import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, inspect

from ..crud import Field, Resource
from ..extensions import db
from ..models import (APP_IDS, ROLES, Announcement, ApiCredential, ApiUsage, AuditLog, EmailLog, LoginEvent,
                      Notification, Passkey, Setting, User)
from ..registry import APPS
from ..services.audit import audit
from .common import admin_required, make_bp

bp = make_bp("admin")

ADMIN_ONLY = {"admin.dashboard", "admin.users", "admin.user_form", "admin.user_action", "admin.activity", "admin.usage",
              "admin.settings", "admin.audit", "admin.email_log", "admin.system"}


@bp.before_request
def admin_gate():
    ep = request.endpoint or ""
    if current_user.is_authenticated and not current_user.is_admin:
        if ep in ADMIN_ONLY or ep.startswith("admin.announcements") or ep.startswith("admin.credentials"):
            if ep == "admin.dashboard":
                return redirect(url_for("admin.profile"))
            abort(403)


Resource("admin", "announcements", Announcement, "Announcements", [
    Field("title", required=True), Field("body", type="text"),
    Field("level", type="select", choices=["info", "warning", "critical"]), Field("active", type="bool", default=True),
], singular="Announcement", order_by=Announcement.created_at.desc(), subtitle="Active announcements show as a banner at the top of every app.").register(bp)

Resource("admin", "credentials", ApiCredential, "Credentials", [
    Field("provider", required=True), Field("label"), Field("key_hint", "Key (last 4)", help="Store only a hint here; real secrets belong in environment variables."),
    Field("scope"), Field("expires_on", type="date"), Field("active", type="bool", default=True),
], singular="Credential", order_by=ApiCredential.provider, subtitle="Integration credentials. Only key hints are stored; secrets live in the environment.").register(bp)


@bp.route("/")
def dashboard():
    now = datetime.utcnow()
    d24 = now - timedelta(hours=24)
    users = User.query.all()
    logins24 = LoginEvent.query.filter(LoginEvent.at >= d24, LoginEvent.success.is_(True)).all()
    failed24 = LoginEvent.query.filter(LoginEvent.at >= d24, LoginEvent.success.is_(False)).all()
    stats = dict(users=len(users), active=sum(1 for u in users if u.is_active_flag), locked=sum(1 for u in users if u.locked),
                 mustpw=sum(1 for u in users if u.must_change_pw), logins24=len(logins24), ips=len({l.ip for l in logins24}),
                 failed24=len(failed24), sessions=len({l.user_id for l in logins24}),
                 email24=EmailLog.query.filter(EmailLog.at >= d24).count(), emailfail=EmailLog.query.filter(EmailLog.at >= d24, EmailLog.status == "failed").count(),
                 adminacts=AuditLog.query.filter(AuditLog.at >= now - timedelta(days=7), AuditLog.app == "admin").count())
    days = [(date.today() - timedelta(days=i)) for i in range(13, -1, -1)]
    ev14 = LoginEvent.query.filter(LoginEvent.at >= datetime.combine(days[0], datetime.min.time()), LoginEvent.success.is_(True)).all()
    per_day = defaultdict(int)
    for e in ev14:
        per_day[e.at.date()] += 1
    logins_chart = dict(type="bar", data=dict(labels=[d.strftime("%b %d") for d in days], datasets=[dict(label="Logins", data=[per_day[d] for d in days])]))
    ev7 = [e for e in ev14 if e.at >= now - timedelta(days=7)]
    per_hour = [0] * 24
    for e in ev7:
        per_hour[e.at.hour] += 1
    hour_chart = dict(type="bar", data=dict(labels=[f"{h:02d}" for h in range(24)], datasets=[dict(label="Logins", data=per_hour, backgroundColor="#10b981")]))
    ev28 = LoginEvent.query.filter(LoginEvent.at >= now - timedelta(days=28), LoginEvent.success.is_(True)).all()
    heat = [[0] * 24 for _ in range(7)]
    for e in ev28:
        heat[e.at.weekday()][e.at.hour] += 1
    hmax = max(max(r) for r in heat) or 1
    top = (db.session.query(User, func.count(LoginEvent.id)).join(LoginEvent, LoginEvent.user_id == User.id)
           .filter(LoginEvent.at >= now - timedelta(days=30), LoginEvent.success.is_(True)).group_by(User.id).order_by(func.count(LoginEvent.id).desc()).limit(8).all())
    d7 = [(date.today() - timedelta(days=i)) for i in range(6, -1, -1)]
    spend = defaultdict(float)
    for u in ApiUsage.query.filter(ApiUsage.day >= d7[0]).all():
        spend[u.day] += u.cost or 0
    spend_chart = dict(type="bar", money=True, data=dict(labels=[d.strftime("%a") for d in d7], datasets=[dict(label="API spend", data=[round(spend[d], 2) for d in d7])]))
    access = {a: sum(1 for u in users if u.is_active_flag and u.can_access(a)) for a in APP_IDS}
    recent = AuditLog.query.order_by(AuditLog.at.desc()).limit(12).all()
    recently_active = User.query.filter(User.last_login_at.isnot(None)).order_by(User.last_login_at.desc()).limit(8).all()
    fail_by_user = defaultdict(int)
    fail_by_ip = defaultdict(int)
    for f in failed24:
        fail_by_user[f.username] += 1
        fail_by_ip[f.ip] += 1
    return render_template("admin/dashboard.html", s=stats, logins_chart=logins_chart, hour_chart=hour_chart, heat=heat, hmax=hmax,
                           top=top, spend_chart=spend_chart, spend7=sum(spend.values()), access=access, recent=recent,
                           recently_active=recently_active, fail_by_user=fail_by_user, fail_by_ip=fail_by_ip, total14=len(ev14))


# ------------------------------------------------------------------ users
@bp.route("/users/")
def users():
    q = User.query
    if request.args.get("role"):
        q = q.filter_by(role=request.args["role"])
    if request.args.get("q"):
        t = f"%{request.args['q']}%"
        q = q.filter(db.or_(User.name.ilike(t), User.email.ilike(t), User.username.ilike(t)))
    return render_template("admin/users.html", users=q.order_by(User.id).all(), roles=ROLES)


@bp.route("/users/new", methods=["GET", "POST"], endpoint="user_new")
@bp.route("/users/<int:uid>", methods=["GET", "POST"], endpoint="user_form")
def user_form(uid=None):
    if not current_user.is_admin:
        abort(403)
    u = db.session.get(User, uid) if uid else None
    if uid and not u:
        abort(404)
    if request.method == "POST":
        f = request.form
        role = f.get("role", "analyst")
        if role == "super_admin" and current_user.role != "super_admin":
            abort(403)
        if u and u.role == "super_admin" and current_user.role != "super_admin":
            abort(403)
        new = u is None
        if new:
            if not f.get("username") or not f.get("email") or not f.get("name"):
                flash("Name, username and email are required.", "error")
                return render_template("admin/user_form.html", u=None, roles=ROLES, apps=APPS, f=f), 400
            if User.query.filter((User.username == f["username"].strip().lower()) | (User.email == f["email"].strip().lower())).first():
                flash("That username or email is already taken.", "error")
                return render_template("admin/user_form.html", u=None, roles=ROLES, apps=APPS, f=f), 400
            u = User(username=f["username"].strip().lower())
            db.session.add(u)
        u.name = f.get("name", u.name).strip()
        u.email = f.get("email", u.email).strip().lower()
        u.title = f.get("title")
        u.role = role
        u.app_access = ",".join(a for a in APP_IDS if f.get(f"app_{a}"))
        u.is_active_flag = bool(f.get("active"))
        temp = None
        if new or f.get("password"):
            temp = f.get("password") or secrets.token_urlsafe(9)
            u.set_password(temp)
            u.must_change_pw = True
        db.session.flush()
        audit("admin", "create" if new else "update", "users", u.id, f"{u.username} ({u.role}) apps={u.app_access}")
        if new:
            from ..models import EmailLog
            db.session.add(EmailLog(to_addr=u.email, subject="Your Alladin Family Office account", kind="invite"))
        db.session.commit()
        flash(f"User {u.username} {'created' if new else 'saved'}." + (f" Temporary password: {temp}" if temp else ""), "success")
        return redirect(url_for(".users"))
    return render_template("admin/user_form.html", u=u, roles=ROLES, apps=APPS, f=None)


@bp.route("/users/<int:uid>/<action>", methods=["POST"])
def user_action(uid, action):
    u = db.session.get(User, uid) or abort(404)
    if u.role == "super_admin" and current_user.role != "super_admin":
        abort(403)
    if action == "unlock":
        u.locked = False
        msg = f"{u.username} unlocked."
    elif action == "lock":
        if u.id == current_user.id:
            abort(400)
        u.locked = True
        msg = f"{u.username} locked."
    elif action == "reset":
        temp = secrets.token_urlsafe(9)
        u.set_password(temp)
        u.must_change_pw = True
        msg = f"Password reset for {u.username}. Temporary password: {temp}"
        db.session.add(EmailLog(to_addr=u.email, subject="Password reset", kind="reset"))
    elif action == "delete":
        if u.id == current_user.id:
            abort(400)
        u.is_active_flag = False
        u.locked = True
        msg = f"{u.username} deactivated."
    else:
        abort(400)
    audit("admin", action, "users", u.id, msg.split(" Temporary")[0])
    db.session.commit()
    flash(msg, "success")
    return redirect(url_for(".users"))


# ------------------------------------------------------------------ logs
@bp.route("/activity/")
def activity():
    q = LoginEvent.query
    if request.args.get("ok") == "0":
        q = q.filter_by(success=False)
    pag = q.order_by(LoginEvent.at.desc()).paginate(page=int(request.args.get("page", 1)), per_page=60, error_out=False)
    return render_template("admin/activity.html", pag=pag)


@bp.route("/usage/")
def usage():
    since = date.today() - timedelta(days=29)
    rows = ApiUsage.query.filter(ApiUsage.day >= since).all()
    days = [since + timedelta(days=i) for i in range(30)]
    by = defaultdict(lambda: defaultdict(float))
    for r in rows:
        by[f"{r.provider} · {r.app}"][r.day] += r.cost or 0
    chart = dict(type="bar", money=True, options=dict(scales=dict(x=dict(stacked=True), y=dict(stacked=True))),
                 data=dict(labels=[d.strftime("%b %d") for d in days], datasets=[dict(label=k, data=[round(v[d], 2) for d in days]) for k, v in by.items()]))
    agg = defaultdict(lambda: [0, 0.0])
    for r in rows:
        agg[(r.provider, r.app)][0] += r.calls
        agg[(r.provider, r.app)][1] += r.cost or 0
    total = sum(v[1] for v in agg.values())
    return render_template("admin/usage.html", chart=chart, agg=sorted(agg.items(), key=lambda x: -x[1][1]), total=total)


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    items = Setting.query.filter_by(scope="platform").order_by(Setting.id).all()
    if request.method == "POST":
        for s in items:
            if f"s_{s.id}" in request.form:
                s.value = request.form[f"s_{s.id}"]
        audit("admin", "update", "settings", None, "Platform settings saved")
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for(".settings"))
    return render_template("admin/settings.html", items=items)


@bp.route("/audit/", endpoint="audit")
def audit_view():
    q = AuditLog.query
    for k in ("app", "action"):
        if request.args.get(k):
            q = q.filter(getattr(AuditLog, k) == request.args[k])
    if request.args.get("q"):
        q = q.filter(AuditLog.detail.ilike(f"%{request.args['q']}%"))
    pag = q.order_by(AuditLog.at.desc()).paginate(page=int(request.args.get("page", 1)), per_page=60, error_out=False)
    apps = [r[0] for r in db.session.query(AuditLog.app).distinct() if r[0]]
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct() if r[0]]
    return render_template("admin/audit.html", pag=pag, apps=sorted(apps), actions=sorted(actions))




@bp.route("/email-log/")
def email_log():
    pag = EmailLog.query.order_by(EmailLog.at.desc()).paginate(page=int(request.args.get("page", 1)), per_page=60, error_out=False)
    return render_template("admin/email_log.html", pag=pag)


@bp.route("/system/")
def system():
    insp = inspect(db.engine)
    counts = []
    for t in sorted(insp.get_table_names()):
        n = db.session.execute(db.text(f'select count(*) from "{t}"')).scalar()
        counts.append((t, n))
    version = db.session.execute(db.text("select version()")).scalar()
    size = db.session.execute(db.text("select pg_size_pretty(pg_database_size(current_database()))")).scalar()
    try:
        rev = db.session.execute(db.text("select version_num from alembic_version")).scalar()
    except Exception:
        db.session.rollback()
        rev = None
    return render_template("admin/system.html", counts=counts, version=version, size=size, rev=rev)


# ------------------------------------------------------------------ account
@bp.route("/profile/", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        f = request.form
        if f.get("action") == "password":
            if not current_user.check_password(f.get("current", "")):
                flash("Current password is wrong.", "error")
            elif len(f.get("new", "")) < 10:
                flash("New password must be at least 10 characters.", "error")
            elif f.get("new") != f.get("confirm"):
                flash("New passwords don't match.", "error")
            else:
                current_user.set_password(f["new"])
                current_user.must_change_pw = False
                audit("admin", "password", "users", current_user.id, "Changed own password")
                db.session.commit()
                flash("Password changed.", "success")
                return redirect(url_for(".profile"))
        else:
            current_user.name = f.get("name", current_user.name).strip() or current_user.name
            current_user.title = f.get("title")
            current_user.color = f.get("color") or current_user.color
            audit("admin", "update", "users", current_user.id, "Updated own profile")
            db.session.commit()
            flash("Profile saved.", "success")
            return redirect(url_for(".profile"))
    return render_template("admin/profile.html", force=request.args.get("force"),
                           logins=LoginEvent.query.filter_by(user_id=current_user.id).order_by(LoginEvent.at.desc()).limit(10).all())


@bp.route("/notifications/", methods=["GET", "POST"])
def notifications():
    if request.method == "POST":
        q = Notification.query.filter_by(user_id=current_user.id)
        if request.form.get("id"):
            q = q.filter_by(id=int(request.form["id"]))
        q.update({"read": True})
        db.session.commit()
        flash("Marked as read.", "success")
        return redirect(url_for(".notifications"))
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.at.desc()).all()
    return render_template("admin/notifications.html", items=items)


@bp.route("/passkeys/", methods=["GET", "POST"])
def passkeys():
    if request.method == "POST":
        pk = db.session.get(Passkey, int(request.form["id"])) or abort(404)
        if pk.user_id != current_user.id and not current_user.is_admin:
            abort(403)
        if request.form.get("action") == "rename":
            pk.name = request.form.get("name") or pk.name
            msg = "Passkey renamed."
        else:
            db.session.delete(pk)
            msg = "Passkey revoked."
        audit("admin", "passkey", "passkeys", pk.id, msg)
        db.session.commit()
        flash(msg, "success")
        return redirect(url_for(".passkeys"))
    mine = Passkey.query.filter_by(user_id=current_user.id).all()
    others = Passkey.query.filter(Passkey.user_id != current_user.id).all() if current_user.is_admin else []
    return render_template("admin/passkeys.html", mine=mine, others=others)

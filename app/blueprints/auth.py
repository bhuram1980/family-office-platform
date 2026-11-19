from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import LoginEvent, User
from ..services.audit import audit

bp = Blueprint("auth", __name__)

MAX_FAILED = 5


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("public.launch"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        pw = request.form.get("password", "")
        user = User.query.filter((db.func.lower(User.username) == username) | (db.func.lower(User.email) == username)).first()
        ok = bool(user and user.check_password(pw) and user.is_active_flag and not user.locked)
        db.session.add(LoginEvent(user_id=user.id if user else None, username=username, success=ok,
                                  ip=request.headers.get("X-Forwarded-For", request.remote_addr),
                                  user_agent=(request.user_agent.string or "")[:300]))
        if ok:
            user.last_login_at = datetime.utcnow()
            login_user(user, remember=bool(request.form.get("remember")))
            audit("auth", "login", "user", user.id, f"{user.username} signed in", user=user)
            db.session.commit()
            nxt = request.args.get("next")
            if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("public.launch"))
        if user and not user.locked:
            recent = (LoginEvent.query.filter_by(user_id=user.id).order_by(LoginEvent.at.desc()).limit(MAX_FAILED).all())
            if len(recent) >= MAX_FAILED - 1 and all(not e.success for e in recent[:MAX_FAILED - 1]):
                user.locked = True
                audit("auth", "lock", "user", user.id, f"{user.username} locked after {MAX_FAILED} failed sign-ins")
        db.session.commit()
        flash("That username and password don't match, or the account is locked.", "error")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("auth", "logout", "user", current_user.id, f"{current_user.username} signed out")
    db.session.commit()
    logout_user()
    flash("You're signed out.", "success")
    return redirect(url_for("auth.login"))

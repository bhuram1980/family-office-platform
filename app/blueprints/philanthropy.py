"""Philanthropy: giving dashboard, grant requests and approvals, recipients, tuition, and DAF reconciliation."""
from collections import defaultdict
from datetime import date, timedelta

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import BankAccount, CashTxn, DAFTxn, Document, Entity, GivingBudget, Grant, Recipient, SignatureRequest, Tuition
from ..models.philanthropy import CAUSES, GRANT_STATUSES
from ..pages import D, M, MS, b, bar_chart, card, chart, donut, form, html, kpis, line_chart, link, lst, note, pill, render, row, status, table, tabs
from ..services import settings as st
from ..services.audit import audit
from .common import make_bp, write_required

bp = make_bp("philanthropy", "philanthropy")
SETTINGS = [("approval_threshold", "Grants at or above this need a second admin approval", "50000", "number"),
            ("annual_target", "Annual giving target", "1500000", "number"), ("daf_sponsor", "DAF sponsor", "Piedmont Community Foundation")]


def u(ep, **kw):
    return url_for(f"philanthropy.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return Markup(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                  f'<button class="{cls}">{escape(label)}</button></form>')


def rlink(r):
    return link(r.name, u("recipient", rid=r.id), "tk")


def daf_balance():
    return sum(t.amount for t in DAFTxn.query.all())


Resource("philanthropy", "grants", Grant, "Grants Ledger", [
    F("recipient_id", "Recipient", type="fk", fk=Recipient, required=True), F("amount", type="money", required=True), F("requested_on", type="date"),
    F("source", type="select", choices=["DAF", "Foundation", "Personal"]), F("cause", type="select", choices=CAUSES), F("purpose"),
    F("status", type="select", choices=GRANT_STATUSES, form=False, fmt=lambda g: status(g.status)), F("paid_on", type="date", form=False),
    F("method", form=False, list=False), F("reconciled", type="bool", form=False),
], singular="Grant request", order_by=Grant.requested_on.desc(), filters=["status", "source", "cause"], nav="philanthropy.grants_list",
    on_save=lambda g, new: (setattr(g, "requested_by_id", current_user.id), setattr(g, "status", "Requested"),
                            setattr(g, "cause", g.cause or (db.session.get(Recipient, g.recipient_id).cause if g.recipient_id else None))) if new else None,
    after_save=lambda g: u("approvals")).register(bp)

Resource("philanthropy", "recipients", Recipient, "Directory", [
    F("name", required=True), F("kind", type="select", choices=["Charity", "School", "Fund"]), F("cause", type="select", choices=CAUSES), F("ein", "EIN"),
    F("city"), F("contact", list=False), F("email", type="email", list=False), F("verified", "501(c)(3) verified", type="bool"), F("notes", type="text", list=False),
], singular="Recipient", order_by=Recipient.name, filters=["kind", "cause"], nav="philanthropy.directory", row_link=lambda r: u("recipient", rid=r.id)).register(bp)

Resource("philanthropy", "tuition", Tuition, "Tuition", [
    F("student", required=True), F("recipient_id", "School", type="fk", fk=Recipient), F("term"), F("amount", type="money"), F("due", type="date"), F("paid_on", type="date"),
], singular="Tuition bill", order_by=Tuition.due.desc(), nav="philanthropy.dashboard").register(bp)

Resource("philanthropy", "budgets", GivingBudget, "Budgets", [
    F("year", type="int", required=True), F("cause", type="select", choices=CAUSES, required=True), F("amount", type="money"),
], singular="Budget line", order_by=[GivingBudget.year.desc(), GivingBudget.cause], nav="philanthropy.dashboard").register(bp)


@bp.route("/")
def dashboard():
    today = date.today()
    y = int(request.args.get("year", today.year))
    paid = Grant.query.filter(Grant.status == "Paid", db.extract("year", Grant.paid_on) == y).all()
    pending = Grant.query.filter(Grant.status.in_(["Requested", "Approved"])).all()
    target = st.get("philanthropy", "annual_target", 1500000, float)
    given = sum(g.amount for g in paid)
    by_cause = defaultdict(float)
    for g in paid:
        by_cause[g.cause or "Other"] += g.amount
    budgets = {b_.cause: b_.amount for b_ in GivingBudget.query.filter_by(year=y).all()}
    by_m = defaultdict(float)
    for g in paid:
        by_m[g.paid_on.month] += g.amount
    cum, run = [], 0
    for m in range(1, 13):
        run += by_m[m]
        cum.append(round(run))
    top = defaultdict(float)
    for g in paid:
        top[g.recipient.name] += g.amount
    tu = Tuition.query.order_by(Tuition.due.desc()).all()
    overview = [
        kpis([(f"Given in {y}", MS(given), f"{len(paid)} grants", "pos", "#e11d48"), ("Target", MS(target), f"{given / (target or 1) * 100:.0f}% reached", "", "#f59e0b"),
              ("Pending", MS(sum(g.amount for g in pending)), f"{len(pending)} requests", "warn" if pending else "", "#6366f1"),
              ("DAF balance", MS(daf_balance()), "available to grant", "", "#10b981"), ("Recipients", len({g.recipient_id for g in paid}), "this year", "", "#0ea5e9")]),
        row(card("Cumulative giving vs target", chart(dict(type="line", money=True, data=dict(labels=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                                                                                             datasets=[dict(label="Given", data=cum, fill=True),
                                                                                                       dict(label="Target pace", data=[round(target * m / 12) for m in range(1, 13)], borderDash=[4, 4])])), 240)),
            card("By cause", chart(donut(list(by_cause), [round(v) for v in by_cause.values()]), 240))),
        row(card("Top recipients", table(["Recipient", ">Given"], [[n, M(v)] for n, v in sorted(top.items(), key=lambda x: -x[1])[:8]], sortable=False)),
            card("Awaiting decision", lst([(f"{g.recipient.name} · ${g.amount:,.0f}", f"{g.purpose} · requested {g.requested_on:%b %d}", status(g.status)) for g in pending[:8]],
                                          empty="Nothing waiting."), right=("Approvals →", u("approvals")))),
    ]
    summary = [card(f"Budget vs actual · {y}", table(["Cause", ">Budget", ">Given", ">Remaining", ">Used"],
                                                     [[c, M(budgets.get(c, 0)), M(by_cause.get(c, 0)), M(budgets.get(c, 0) - by_cause.get(c, 0), color=True),
                                                       f"{by_cause.get(c, 0) / (budgets.get(c) or 1) * 100:.0f}%"] for c in CAUSES],
                                                     foot=["Total", M(sum(budgets.values())), M(given), M(sum(budgets.values()) - given), ""]),
                       right=("Edit budgets →", u("budgets_list")))]
    grid = defaultdict(lambda: defaultdict(float))
    for g in paid:
        grid[g.recipient.name][g.paid_on.month] += g.amount
    mg = [card(f"Paid grants by month · {y}", table(["Recipient"] + [">" + date(2000, m, 1).strftime("%b") for m in range(1, 13)] + [">Total"],
                                                   [[n] + [M(v[m]) if v[m] else "" for m in range(1, 13)] + [M(sum(v.values()))] for n, v in sorted(grid.items())],
                                                   foot=["Total"] + [M(by_m[m]) if by_m[m] else "" for m in range(1, 13)] + [M(given)]))]
    tuition = [card("Tuition", table(["Student", "School", "Term", ">Amount", "Due", "Status", ""],
                                     [[t.student, t.recipient.name if t.recipient else "—", t.term, M(t.amount), D(t.due), status("Paid") if t.paid_on else
                                       (status("Overdue") if t.due < today else status("Scheduled")), "" if t.paid_on else postbtn(u("pay_tuition", tid=t.id), "Mark paid", "btn sm green")]
                                      for t in tu]), right=("+ Add tuition", u("tuition_new")))]
    years = sorted({g.paid_on.year for g in Grant.query.filter(Grant.paid_on.isnot(None)).all()} | {today.year})
    return render("Philanthropy", [tabs([("overview", "Overview", overview), ("summary", "Summary", summary), ("grid", "Month grid", mg), ("tuition", "Tuition", tuition)])],
                  sub="Alladin Foundation and donor-advised fund",
                  actions=[(str(x), u("dashboard", year=x), "primary" if x == y else "") for x in years] + [("+ New grant", u("grants_new"), "primary")])


@bp.route("/giving/")
def giving():
    gs = Grant.query.filter_by(status="Paid").order_by(Grant.paid_on.desc()).limit(200).all()
    by_y = defaultdict(float)
    for g in Grant.query.filter_by(status="Paid").all():
        by_y[g.paid_on.year] += g.amount
    ys = sorted(by_y)
    return render("Giving", [card("Giving by year", chart(bar_chart([str(x) for x in ys], [round(by_y[x]) for x in ys], "Given", color="#e11d48"), 200)),
                             card("Paid grants", table(["Paid", "Recipient", "Cause", "Purpose", "Source", "Method", ">Amount"],
                                                       [[D(g.paid_on), rlink(g.recipient), g.cause, g.purpose, g.source, g.method, M(g.amount)] for g in gs]))],
                  actions=[("+ New grant", u("grants_new"), "primary")])


@bp.route("/approvals/")
def approvals():
    thr = st.get("philanthropy", "approval_threshold", 50000, float)
    req = Grant.query.filter_by(status="Requested").order_by(Grant.requested_on).all()
    app_ = Grant.query.filter_by(status="Approved").order_by(Grant.approved_on).all()

    def decide(g):
        if not current_user.is_admin:
            return Markup('<span class="small muted">admin decides</span>')
        if g.amount >= thr and g.requested_by_id == current_user.id:
            return Markup('<span class="small muted">needs a different admin</span>')
        return (postbtn(u("decide", gid=g.id, action="approve"), "Approve", "btn sm green") + Markup(" ") +
                postbtn(u("decide", gid=g.id, action="decline"), "Decline", "btn sm"))
    return render("Approvals", [
        note(f"Grants of ${thr:,.0f} or more can't be approved by the person who requested them. Unverified recipients are marked ⚠."),
        card(f"Requested · {len(req)}", table(["Requested", "Recipient", "Purpose", "Source", ">Amount", "Requested by", ""],
                                              [[D(g.requested_on), Markup(("⚠ " if not g.recipient.verified else "")) + rlink(g.recipient), g.purpose, g.source, M(g.amount),
                                                g.requested_by.name if g.requested_by else "—", decide(g)] for g in req], empty="No requests.")),
        card(f"Approved, awaiting payment · {len(app_)}", table(["Approved", "Recipient", ">Amount", "Source", "Approved by", ""],
                                                                [[D(g.approved_on), rlink(g.recipient), M(g.amount), g.source, g.approved_by.name if g.approved_by else "—",
                                                                  postbtn(u("pay", gid=g.id), "Pay", "btn sm green")] for g in app_], empty="Nothing to pay.")),
    ], actions=[("+ New request", u("grants_new"), "primary")])


@bp.route("/grants/<int:gid>/<action>", methods=["POST"])
@write_required
def decide(gid, action):
    g = db.get_or_404(Grant, gid)
    if not current_user.is_admin or g.status != "Requested" or action not in ("approve", "decline"):
        abort(403 if not current_user.is_admin else 400)
    thr = st.get("philanthropy", "approval_threshold", 50000, float)
    if action == "approve" and g.amount >= thr and g.requested_by_id == current_user.id:
        flash("A different admin must approve a grant this size.", "error")
        return redirect(u("approvals"))
    g.status = "Approved" if action == "approve" else "Declined"
    g.approved_by_id, g.approved_on = current_user.id, date.today()
    audit("philanthropy", action, "grant", g.id, str(g))
    db.session.commit()
    flash(f"{g.recipient.name}: {g.status.lower()}.", "success")
    return redirect(u("approvals"))


@bp.route("/grants/<int:gid>/pay", methods=["POST"])
@write_required
def pay(gid):
    g = db.get_or_404(Grant, gid)
    if g.status != "Approved":
        abort(400)
    g.status, g.paid_on = "Paid", date.today()
    if g.source == "DAF":
        if daf_balance() < g.amount:
            db.session.rollback()
            flash("Not enough in the donor-advised fund.", "error")
            return redirect(u("approvals"))
        g.method = "DAF grant"
        db.session.add(DAFTxn(day=date.today(), kind="Grant", amount=-g.amount, memo=f"Grant to {g.recipient.name}", grant_id=g.id))
        g.reconciled = True
    else:
        g.method = "Wire"
        ent = Entity.query.filter_by(name="Alladin Foundation").first()
        acct = BankAccount.query.filter_by(entity_id=ent.id).first() if ent else None
        acct = acct or BankAccount.query.filter_by(kind="Operating").first()
        acct.balance = (acct.balance or 0) - g.amount
        db.session.add(CashTxn(bank_account_id=acct.id, day=date.today(), amount=-g.amount, category="Charitable", counterparty=g.recipient.name, memo=g.purpose))
    audit("philanthropy", "pay", "grant", g.id, f"{g} via {g.method}")
    db.session.commit()
    flash(f"Paid ${g.amount:,.0f} to {g.recipient.name} ({g.method}).", "success")
    return redirect(u("approvals"))


@bp.route("/tuition/<int:tid>/pay", methods=["POST"])
@write_required
def pay_tuition(tid):
    t = db.get_or_404(Tuition, tid)
    t.paid_on = date.today()
    audit("philanthropy", "pay", "tuition", t.id, f"{t.student} {t.term}")
    db.session.commit()
    return redirect(u("dashboard", tab="tuition"))


@bp.route("/directory/")
def directory():
    rs = Recipient.query.order_by(Recipient.name).all()
    tot = defaultdict(float)
    last = {}
    for g in Grant.query.filter_by(status="Paid").all():
        tot[g.recipient_id] += g.amount
        last[g.recipient_id] = max(last.get(g.recipient_id, g.paid_on), g.paid_on)
    return render("Directory", [card(None, table(["Recipient", "Type", "Cause", "City", "EIN", "Verified", ">Lifetime giving", "Last gift"],
                                                 [[rlink(r), r.kind, r.cause, r.city, r.ein or "—", status("Current") if r.verified else pill("Unverified", "red"), M(tot[r.id]),
                                                   D(last.get(r.id))] for r in rs]))],
                  actions=[("Export CSV", u("recipients_export")), ("+ Add recipient", u("recipients_new"), "primary")])


@bp.route("/directory/<int:rid>/")
def recipient(rid):
    r = db.get_or_404(Recipient, rid)
    gs = sorted(r.grants, key=lambda g: g.requested_on, reverse=True)
    paid = [g for g in gs if g.status == "Paid"]
    return render(r.name, [kpis([("Lifetime giving", M(sum(g.amount for g in paid))), ("Grants", len(paid)), ("Cause", r.cause or "—"),
                                 ("501(c)(3)", status("Current") if r.verified else pill("Unverified", "red"))]),
                           card("Grants", table(["Requested", "Purpose", "Source", ">Amount", "Status", "Paid"], [[D(g.requested_on), g.purpose, g.source, M(g.amount), status(g.status), D(g.paid_on)]
                                                                                                             for g in gs])),
                           card("Contact", html(f'<div style="padding:12px 16px" class="small">{escape(r.contact or "")} · {escape(r.email or "")} · {escape(r.city or "")}<br>EIN {escape(r.ein or "—")}'
                                                f'<p>{escape(r.notes or "")}</p></div>'))],
                  back=("Directory", u("directory")), active="philanthropy.directory", actions=[("Edit", u("recipients_edit", obj_id=r.id)), ("+ Grant", u("grants_new"), "primary")])


@bp.route("/reconciliation/")
def reconciliation():
    txns = DAFTxn.query.order_by(DAFTxn.day.desc()).all()
    unmatched_grants = Grant.query.filter(Grant.status == "Paid", Grant.source == "DAF", Grant.reconciled.is_(False)).order_by(Grant.paid_on.desc()).all()
    open_tx = [t for t in txns if t.kind == "Grant" and not t.grant_id]
    rows = []
    for t in open_tx:
        cands = [g for g in unmatched_grants if abs(g.amount + t.amount) < 0.01 and abs((g.paid_on - t.day).days) <= 10]
        btn = (postbtn(u("match", tid=t.id), f"Match to {cands[0].recipient.name}", "btn sm green", f'<input type="hidden" name="gid" value="{cands[0].id}">')
               if cands else Markup('<span class="small muted">no candidate</span>'))
        rows.append([D(t.day), t.memo, M(t.amount), btn])
    bal_rows = []
    run = 0
    for t in sorted(txns, key=lambda x: (x.day, x.id)):
        run += t.amount
        bal_rows.append([D(t.day), t.kind, t.memo, M(t.amount, color=True), M(run), status("Reconciled") if (t.kind != "Grant" or t.grant_id) else status("Unreconciled")])
    return render("Reconciliation", [
        kpis([("DAF balance", M(daf_balance())), ("Unmatched DAF grants", len(open_tx), "", "warn" if open_tx else ""), ("Paid grants not on statement", len(unmatched_grants), "", "warn" if unmatched_grants else "")]),
        card("DAF statement lines without a matching grant", table(["Date", "Memo", ">Amount", ""], rows, empty="Every statement grant is matched.")),
        card("Paid DAF grants not yet on the statement", table(["Paid", "Recipient", ">Amount"], [[D(g.paid_on), g.recipient.name, M(g.amount)] for g in unmatched_grants], empty="None.")),
        card("DAF ledger", table(["Date", "Type", "Memo", ">Amount", ">Balance", "Status"], list(reversed(bal_rows)), max_height=420)),
    ], sub=f"Sponsor: {st.get('philanthropy', 'daf_sponsor', 'Piedmont Community Foundation')}")


@bp.route("/reconciliation/<int:tid>/match", methods=["POST"])
@write_required
def match(tid):
    t = db.get_or_404(DAFTxn, tid)
    g = db.get_or_404(Grant, int(request.form["gid"]))
    t.grant_id = g.id
    g.reconciled = True
    audit("philanthropy", "reconcile", "grant", g.id, f"DAF line {t.id}")
    db.session.commit()
    flash(f"Matched {g.recipient.name}.", "success")
    return redirect(u("reconciliation"))


@bp.route("/documents/")
def documents():
    ent = Entity.query.filter_by(name="Alladin Foundation").first()
    docs = Document.query.filter(Document.deleted_at.is_(None), Document.entity_id == (ent.id if ent else -1)).all()
    env = SignatureRequest.query.filter(SignatureRequest.title.ilike("%grant%")).all()
    return render("Documents", [
        card("Grant agreements (e-signature)", table(["Envelope", "Status", "Sent"], [[link(r.title, url_for("documents.esign_detail", rid=r.id)), status(r.status), D(r.sent_at)] for r in env],
                                                    empty="No grant agreements yet."), right=("New envelope →", url_for("documents.esign_new"))),
        card("Foundation documents", table(["Document", "Type", "Received"], [[link(d.filename, url_for("documents.doc", did=d.id)), d.kind or d.proposed_kind, D(d.received_at)] for d in docs],
                                           empty="No documents filed to the Foundation yet — upload in Documents and assign the entity “Alladin Foundation”."),
             right=("Upload →", url_for("documents.inbox"))),
    ])


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    r = st.handle("philanthropy", SETTINGS)
    if r:
        return r
    return render("Settings", [card("Giving rules", form(u("settings"), st.form_fields("philanthropy", SETTINGS)), flush=False)])

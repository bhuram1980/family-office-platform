"""IR Portal: what co-investors see. Investors only ever see their own profiles; office staff can view as any investor and answer messages."""
from collections import defaultdict
from datetime import date, datetime

from flask import Response, abort, flash, redirect, request, session, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import (Deal, InvestorPosition, InvestorProfile, IRDocument, IRInterest, IRMessage, IROffering, LoginEvent, Property, User)
from ..pages import D, M, MS, b, bar_chart, card, chart, donut, form, html, kpis, line_chart, link, lst, note, pill, render, row, status, table, tabs
from ..services.audit import audit
from .common import make_bp

bp = make_bp("ir-portal", "ir_portal")


def u(ep, **kw):
    return url_for(f"ir_portal.{ep}", **kw)


def _csrf():
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return Markup(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                  f'<button class="{cls}">{escape(label)}</button></form>')


def is_staff():
    return current_user.role != "investor"


def investors():
    return User.query.filter_by(role="investor").order_by(User.name).all()


def viewer():
    """The investor whose portal is being shown."""
    if not is_staff():
        return current_user
    if request.args.get("as", "").isdigit():
        session["ir_as"] = int(request.args["as"])
    uid = session.get("ir_as")
    v = db.session.get(User, uid) if uid else None
    if not v or v.role != "investor":
        v = investors()[0] if investors() else None
    return v


def my_profiles(v):
    return InvestorProfile.query.filter_by(user_id=v.id).order_by(InvestorProfile.id).all() if v else []


def own_profile(pid, v):
    p = db.get_or_404(InvestorProfile, pid)
    if p.user_id != v.id:
        abort(404)
    return p


def investor_write():
    """Investors may act on their own portal; staff need write access."""
    if is_staff() and not current_user.can_write:
        abort(403)


def page(title, blocks, v, **kw):
    if is_staff():
        sel = "".join(f'<option value="{x.id}" {"selected" if v and x.id == v.id else ""}>{escape(x.name)}</option>' for x in investors())
        bar = (f'<form method="get" style="display:flex;gap:8px;align-items:center;background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:8px 12px;margin-bottom:14px">'
               f'<span class="small"><b>Office view</b> — viewing the portal as</span><select class="inp" name="as" onchange="this.form.submit()" style="width:auto">{sel}</select>'
               f'<span style="flex:1"></span><a class="btn sm" href="{u("office_messages")}">Investor messages</a><a class="btn sm" href="{u("offerings_list")}">Manage offerings</a></form>')
        blocks = [html(bar)] + blocks
    return render(title, blocks, **kw)


def positions(v):
    return [p for pr in my_profiles(v) for p in pr.positions]


Resource("ir-portal", "offerings", IROffering, "Offerings", [
    F("title", required=True), F("deal_id", "Deal", type="fk", fk=Deal), F("asset_class"), F("location"), F("raise_amount", "Allocation offered", type="money"),
    F("min_check", "Minimum", type="money"), F("target_irr", "Target IRR %", type="float"), F("target_close", type="date"),
    F("status", type="select", choices=["Open", "Closed"]), F("summary", type="text", list=False),
], singular="Offering", order_by=IROffering.target_close, nav="ir_portal.deals", readonly=False).register(bp)


@bp.before_request
def staff_only_admin_pages():
    if request.endpoint and request.endpoint.startswith("ir_portal.offerings_") and not is_staff():
        abort(403)


@bp.route("/")
def dashboard():
    v = viewer()
    if not v:
        return render("IR Portal", [note("No investors yet. Create a user with the investor role in Admin.")])
    pos = positions(v)
    contributed = sum(p.contributed or 0 for p in pos)
    nav = sum(p.nav for p in pos)
    dist = sum(p.distributions or 0 for p in pos)
    commit = sum(p.commitment or 0 for p in pos)
    by_cls = defaultdict(float)
    for p in pos:
        by_cls[p.investment.asset_class] += p.nav
    unread = IRMessage.query.filter_by(investor_id=v.id, read_by_investor=False).count()
    newdocs = IRDocument.query.join(InvestorProfile).filter(InvestorProfile.user_id == v.id, IRDocument.viewed_at.is_(None)).count()
    offs = IROffering.query.filter_by(status="Open").all()
    return page(f"Welcome back, {v.first_name}", [
        kpis([("Net asset value", MS(nav), f"{len(pos)} positions", "", "#2563eb"), ("Contributed", MS(contributed), f"of {MS(commit)} committed", "", "#0ea5e9"),
              ("Distributions", MS(dist), "received to date", "pos", "#10b981"), ("TVPI", f"{(nav + dist) / contributed:.2f}x" if contributed else "—", "total value / paid-in", "", "#8b5cf6")]),
        row(card("Allocation", chart(donut(list(by_cls), [round(x) for x in by_cls.values()]), 230)),
            card("Positions", table(["Investment", "Profile", ">NAV", ">TVPI"], [[link(p.investment.name, u("investment", pid=p.id)), p.profile.name, M(p.nav),
                                                                                f"{p.tvpi:.2f}x" if p.tvpi else "—"] for p in sorted(pos, key=lambda x: -x.nav)], sortable=False),
                 right=("All →", u("investments")))),
        row(card("What's new", lst([(f"{newdocs} new document(s)", "Quarterly reports and tax forms", None, "blue" if newdocs else ""),
                                    (f"{unread} unread message(s)", "From the Bhuram Family Office team", None, "blue" if unread else ""),
                                    (f"{len(offs)} open co-investment(s)", "Limited allocations alongside the family", None, "")])),
            card("Open opportunities", lst([(o.title, f"{o.asset_class} · {o.location} · min ${o.min_check or 0:,.0f} · closes {o.target_close:%b %d}", None) for o in offs],
                                           empty="No open offerings."), right=("Deals →", u("deals")))),
    ], v, sub=f"{v.name} · {len(my_profiles(v))} investing profile(s)")


@bp.route("/investments/")
def investments():
    v = viewer()
    pos = positions(v)
    rows = [[link(p.investment.name, u("investment", pid=p.id)), p.profile.name, p.investment.asset_class, f"{p.ownership_pct:g}%", M(p.commitment), M(p.contributed),
             M(p.distributions), M(p.nav), f"{p.tvpi:.2f}x" if p.tvpi else "—", D(p.since)] for p in pos]
    return page("Investments", [card(None, table(["Investment", "Profile", "Class", ">Share", ">Commitment", ">Contributed", ">Distributions", ">NAV", ">TVPI", "Since"], rows,
                                                 foot=["Total", "", "", "", M(sum(p.commitment or 0 for p in pos)), M(sum(p.contributed or 0 for p in pos)),
                                                       M(sum(p.distributions or 0 for p in pos)), M(sum(p.nav for p in pos)), "", ""]))], v)


@bp.route("/investments/<int:pid>/")
def investment(pid):
    v = viewer()
    p = db.get_or_404(InvestorPosition, pid)
    if p.profile.user_id != v.id:
        abort(404)
    i = p.investment
    vals = sorted(i.valuations, key=lambda x: x.day)
    docs = IRDocument.query.filter_by(profile_id=p.profile_id, investment_id=i.id).all()
    return page(i.name, [
        kpis([("Your NAV", M(p.nav)), ("Contributed", M(p.contributed)), ("Distributions", M(p.distributions)), ("TVPI", f"{p.tvpi:.2f}x" if p.tvpi else "—"),
              ("Your share", f"{p.ownership_pct:g}% of the family position")]),
        row(card("Value history (your share)", chart(line_chart([x.day.strftime("%b %y") for x in vals], {"NAV": [round(x.fmv * p.ownership_pct / 100) for x in vals]}, fill=True), 230)),
            card("About", table(["", ""], [["Asset class", i.asset_class], ["Sector", i.sector or "—"], ["Sponsor", i.sponsor or "Bhuram Family Office"],
                                           ["Location", f"{i.city or ''} {i.state or ''}"], ["Vintage", i.vintage or "—"], ["Profile", p.profile.name]], sortable=False))),
        card("Documents", table(["Document", "Period", ""], [[d.title, d.period, link("Download", u("doc_download", did=d.id))] for d in docs], empty="None yet.")),
    ], v, back=("Investments", u("investments")), active="ir_portal.investments")


@bp.route("/sites/")
def sites():
    v = viewer()
    by_inv = {p.investment_id: p for p in positions(v)}
    props = Property.query.filter(Property.investment_id.in_(list(by_inv) or [-1])).all()
    rows = [[b(pr.name), pr.kind, f"{pr.city}, {pr.state}", pr.units or "—", f"{pr.occupancy or 0:.1f}%", M((pr.fmv or 0) * by_inv[pr.investment_id].ownership_pct / 100),
             by_inv[pr.investment_id].profile.name] for pr in props]
    return page("Sites", [card("Properties you own a share of", table(["Property", "Type", "Location", ">Units", ">Occupancy", ">Your share of value", "Profile"], rows,
                                                                      empty="None of your positions hold real estate."))], v)


@bp.route("/profiles/", methods=["GET", "POST"])
def profiles():
    v = viewer()
    if request.method == "POST":
        investor_write()
        p = own_profile(int(request.form["pid"]), v)
        p.address = request.form.get("address", p.address)[:200]
        b4 = (request.form.get("bank_last4") or "").strip()
        if b4 and (len(b4) != 4 or not b4.isdigit()):
            flash("Bank account: enter the last four digits only.", "error")
            return redirect(u("profiles"))
        p.bank_last4 = b4 or p.bank_last4
        audit("ir-portal", "update", "investor_profile", p.id, "address/bank updated")
        db.session.commit()
        flash(f"{p.name} updated. The office will verify any bank change by phone before the next distribution.", "success")
        return redirect(u("profiles"))
    blocks = []
    for p in my_profiles(v):
        blocks.append(card(f"{p.name} · {p.kind}", [table(["", ""], [["Tax ID", f"•••-••-{p.tax_id_last4}"], ["Distribution account", f"•••• {p.bank_last4}"],
                                                                    ["Address", p.address], ["Accredited", "Yes" if p.accredited else "No"],
                                                                    ["Positions", len(p.positions)]], sortable=False),
                                                    form(u("profiles"), [("pid", "", "hidden", p.id), ("address", "Mailing address", "text", p.address),
                                                                         ("bank_last4", "New distribution account (last 4)", "text", "")], submit="Update")], flush=False))
    return page("Profiles", blocks or [note("No investing profiles yet.")], v)


@bp.route("/deals/")
def deals():
    v = viewer()
    offs = IROffering.query.order_by(IROffering.status.desc(), IROffering.target_close).all()
    mine = {(i.offering_id): i for i in IRInterest.query.join(InvestorProfile).filter(InvestorProfile.user_id == v.id).all()} if v else {}
    blocks = []
    for o in offs:
        it = mine.get(o.id)
        blocks.append(card(o.title, html(f'<div style="padding:12px 16px"><div class="small muted">{escape(o.asset_class or "")} · {escape(o.location or "")} · target IRR {o.target_irr or 0:.0f}% · '
                                         f'min ${o.min_check or 0:,.0f} · closes {o.target_close:%b %d, %Y}</div><p class="small">{escape(o.summary or "")}</p>'
                                         + (f'<p>{status(it.status)} ${it.amount or 0:,.0f} from {escape(it.profile.name)}</p>' if it else "") +
                                         f'<a class="btn sm primary" href="{u("offering", oid=o.id)}">{"View / update" if it else "Indicate interest"}</a></div>'),
                           right=None, sub=o.status))
    return page("Deals", blocks or [note("No offerings right now.")], v)


@bp.route("/deals/<int:oid>/", methods=["GET", "POST"])
def offering(oid):
    v = viewer()
    o = db.get_or_404(IROffering, oid)
    profs = my_profiles(v)
    if request.method == "POST":
        investor_write()
        if o.status != "Open":
            abort(400)
        p = own_profile(int(request.form["profile_id"]), v)
        action = request.form.get("action", "indicate")
        it = IRInterest.query.filter_by(offering_id=o.id, profile_id=p.id).first()
        if action == "withdraw":
            if it:
                it.status = "Withdrawn"
        else:
            amt = float(request.form.get("amount") or 0)
            if amt < (o.min_check or 0):
                flash(f"The minimum is ${o.min_check:,.0f}.", "error")
                return redirect(u("offering", oid=o.id))
            it = it or IRInterest(offering_id=o.id, profile_id=p.id)
            it.amount, it.status = amt, "Committed" if action == "commit" else "Indicated"
            db.session.add(it)
            db.session.add(IRMessage(investor_id=v.id, from_id=current_user.id, subject=f"{it.status}: {o.title}",
                                     body=f"{p.name} {it.status.lower()} ${amt:,.0f} to {o.title}.", read_by_investor=True, read_by_office=False))
        audit("ir-portal", action, "offering", o.id, f"{p.name}")
        db.session.commit()
        flash("Thanks — the office has been notified.", "success")
        return redirect(u("deals"))
    its = IRInterest.query.filter(IRInterest.offering_id == o.id, IRInterest.profile_id.in_([p.id for p in profs] or [-1])).all()
    fields = [("profile_id", "Invest from", "select", [(p.id, p.name) for p in profs]), ("amount", "Amount", "number", o.min_check),
              ("action", "", "select", [("indicate", "Indicate interest (non-binding)"), ("commit", "Commit"), ("withdraw", "Withdraw")])]
    blocks = [kpis([("Allocation", M(o.raise_amount)), ("Minimum", M(o.min_check)), ("Target IRR", f"{o.target_irr or 0:.0f}%"), ("Closes", D(o.target_close))]),
              card("Summary", html(f'<div style="padding:12px 16px" class="small">{escape(o.summary or "")}</div>'))]
    if its:
        blocks.append(card("Your indications", table(["Profile", ">Amount", "Status"], [[i.profile.name, M(i.amount), status(i.status)] for i in its])))
    if is_staff():
        alli = IRInterest.query.filter_by(offering_id=o.id).all()
        blocks.append(card("All investor interest (office only)", table(["Profile", "Investor", ">Amount", "Status"], [[i.profile.name, i.profile.user.name, M(i.amount), status(i.status)] for i in alli])))
    if o.status == "Open" and profs:
        blocks.append(card("Respond", form(u("offering", oid=o.id), fields, submit="Submit"), flush=False))
    return page(o.title, blocks, v, back=("Deals", u("deals")), active="ir_portal.deals")


@bp.route("/documents/")
def documents():
    v = viewer()
    docs = IRDocument.query.join(InvestorProfile).filter(InvestorProfile.user_id == v.id).order_by(IRDocument.created_at.desc()).all() if v else []
    kind = request.args.get("kind")
    if kind:
        docs = [d for d in docs if d.kind == kind]
    chips = "".join(f'<a class="chip {"on" if (kind or "") == k else ""}" href="{u("documents", kind=k) if k else u("documents")}">{k or "All"}</a>' for k in ["", "Quarterly report", "K-1"])
    return page("Documents", [html(f'<div class="chips">{chips}</div>'),
                              card(None, table(["Document", "Profile", "Type", "Period", "Posted", ""],
                                               [[Markup("<b>" if not d.viewed_at else "") + escape(d.title) + Markup("</b>" if not d.viewed_at else ""), d.profile.name, d.kind, d.period,
                                                 D(d.created_at), link("Download", u("doc_download", did=d.id))] for d in docs], empty="No documents."))], v)


@bp.route("/documents/<int:did>/download")
def doc_download(did):
    v = viewer()
    d = db.get_or_404(IRDocument, did)
    if d.profile.user_id != v.id:
        abort(404)
    if not is_staff() and not d.viewed_at:
        d.viewed_at = datetime.utcnow()
        db.session.commit()
    data = db.session.query(IRDocument.content).filter_by(id=d.id).scalar() or b""
    fn = "".join(c for c in d.title if c.isalnum() or c in " -_")[:80] + ".pdf"
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@bp.route("/messages/", methods=["GET", "POST"])
def messages():
    v = viewer()
    if request.method == "POST":
        investor_write()
        body = (request.form.get("body") or "").strip()
        if body:
            db.session.add(IRMessage(investor_id=v.id, from_id=current_user.id, subject=request.form.get("subject") or "Message", body=body[:4000],
                                     read_by_investor=not is_staff(), read_by_office=is_staff()))
            audit("ir-portal", "message", "ir_message", v.id, "sent")
            db.session.commit()
            flash("Message sent.", "success")
        return redirect(u("messages"))
    msgs = IRMessage.query.filter_by(investor_id=v.id).order_by(IRMessage.at).all() if v else []
    if not is_staff():
        for m in msgs:
            m.read_by_investor = True
        db.session.commit()
    items = "".join(
        f'<div style="display:flex;justify-content:{"flex-end" if m.from_id == v.id else "flex-start"};margin:8px 0"><div style="max-width:70%;background:{"#2563eb" if m.from_id == v.id else "#f1f5f9"};'
        f'color:{"#fff" if m.from_id == v.id else "inherit"};border-radius:12px;padding:10px 12px"><div class="small" style="opacity:.8"><b>{escape(m.sender.name if m.sender else "")}</b> · {m.at:%b %d, %H:%M} UTC'
        f'{" · " + str(escape(m.subject)) if m.subject else ""}</div><div style="white-space:pre-wrap">{escape(m.body)}</div></div></div>' for m in msgs)
    return page("Messages", [card("Conversation with the Bhuram Family Office" if not is_staff() else f"Conversation with {v.name}", html(f'<div style="padding:8px 16px">{items or "No messages yet."}</div>')),
                             card("New message", form(u("messages"), [("subject", "Subject", "text", ""), ("body", "Message", "textarea", "")], submit="Send"), flush=False)], v)


@bp.route("/office/messages/")
def office_messages():
    if not is_staff():
        abort(403)
    rows = []
    for x in investors():
        ms = IRMessage.query.filter_by(investor_id=x.id).order_by(IRMessage.at.desc()).all()
        unread = len([m for m in ms if not m.read_by_office])
        rows.append([b(x.name), ms[0].subject if ms else "—", D(ms[0].at) if ms else "—", pill(f"{unread} new", "red") if unread else "—",
                     link("Open thread", u("thread", iid=x.id))])
    return render("Investor messages", [card(None, table(["Investor", "Last subject", "Last message", "Unread", ""], rows))], active="ir_portal.messages")


@bp.route("/office/messages/<int:iid>/")
def thread(iid):
    if not is_staff():
        abort(403)
    session["ir_as"] = iid
    for m in IRMessage.query.filter_by(investor_id=iid, read_by_office=False).all():
        m.read_by_office = True
    db.session.commit()
    return redirect(u("messages"))


@bp.route("/profile/")
def profile():
    v = viewer()
    ev = LoginEvent.query.filter_by(user_id=v.id).order_by(LoginEvent.at.desc()).limit(10).all() if v else []
    return page("Profile & security", [
        row(card("Account", table(["", ""], [["Name", v.name], ["Email", v.email], ["Username", v.username], ["Role", "Co-investor"],
                                             ["Last sign-in", ev[0].at.strftime("%b %d, %Y %H:%M UTC") if ev else "—"]], sortable=False)),
            card("Security", html(f'<div style="padding:14px 16px" class="small"><p>Change your password and manage passkeys from your account page.</p>'
                                  f'<a class="btn primary sm" href="{url_for("admin.profile")}">Change password</a> <a class="btn sm" href="{url_for("admin.passkeys")}">Passkeys</a>'
                                  f'<p class="muted" style="margin-top:10px">Accounts lock after 5 failed sign-ins. Bank-detail changes are always confirmed by phone.</p></div>'))),
        card("Recent sign-ins", table(["When (UTC)", "Result", "IP", "Device"], [[e.at.strftime("%b %d, %Y %H:%M"), status("Done") if e.success else pill("Failed", "red"), e.ip,
                                                                               (e.user_agent or "")[:60]] for e in ev], empty="No sign-ins recorded.")),
    ], v)

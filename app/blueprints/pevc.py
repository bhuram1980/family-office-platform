"""PE / VC monitor: private positions from the shared ledger plus operating metrics, GP updates, document coverage and reviews."""
from collections import defaultdict
from datetime import date, timedelta

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from markupsafe import Markup

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import CapitalCall, CompanyMetric, Distribution, GPUpdate, Investment, PEDocument, PEReview, Valuation
from ..pages import (D, M, MS, P, b, bar_chart, bars, card, chart, donut, form, html, kpis, line_chart, link, lst, note, pill, render, row, small,
                     status, table, tabs)
from ..seed.pevc import PRIVATE, quarters
from ..services.audit import audit
from .common import make_bp, write_required

bp = make_bp("pevc", "pevc")


def u(ep, **kw):
    return url_for(f"pevc.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return html(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                f'<button class="{cls}">{label}</button></form>')["html"]


def positions(active=True):
    q = Investment.query.filter(Investment.asset_class.in_(PRIVATE))
    if active:
        q = q.filter(Investment.status == "Active")
    return q.order_by(Investment.fmv.desc()).all()


def ilink(i):
    return link(i.name, u("position", iid=i.id), "tk")


def tvpi(invs):
    paid = sum(i.invested or 0 for i in invs)
    return ((sum(i.fmv or 0 for i in invs) + sum(i.distributions or 0 for i in invs)) / paid) if paid else 0


def attention_items():
    out = []
    today = date.today()
    lq = quarters(1)[0]
    for i in positions():
        if i.attention:
            out.append((i, "Flag", i.attention))
        if not i.last_mark or (today - i.last_mark).days > 150:
            out.append((i, "Stale mark", f"Last mark {i.last_mark:%b %d, %Y}" if i.last_mark else "Never marked"))
        ms = i.metrics
        if len(ms) >= 2 and ms[-1].revenue and ms[-2].revenue and ms[-1].revenue < ms[-2].revenue * 0.95:
            out.append((i, "Revenue down", f"{(ms[-1].revenue / ms[-2].revenue - 1) * 100:.0f}% QoQ in {ms[-1].quarter}"))
        if ms and ms[-1].runway_months is not None and ms[-1].runway_months < 12:
            out.append((i, "Runway", f"{ms[-1].runway_months:.0f} months of cash at current burn"))
        if not PEDocument.query.filter_by(investment_id=i.id, period=lq, kind="Quarterly statement").first():
            out.append((i, "Missing statement", f"{lq} quarterly statement not received"))
    for c in CapitalCall.query.filter_by(status="Pending").all():
        if c.investment.asset_class in PRIVATE and c.due <= today + timedelta(days=14):
            out.append((c.investment, "Call due", f"${c.amount:,.0f} due {c.due:%b %d}"))
    return out


Resource("pevc", "metrics", CompanyMetric, "Operating Metrics", [
    F("investment_id", "Company", type="fk", fk=Investment, required=True), F("quarter", required=True, help="e.g. 2026Q3"),
    F("revenue", type="money"), F("ebitda", "EBITDA", type="money"), F("arr", "ARR", type="money"), F("cash", type="money"),
    F("burn", "Monthly burn", type="money"), F("headcount", type="int"), F("net_debt", type="money"),
], singular="Quarter of metrics", order_by=CompanyMetric.quarter.desc(), nav="pevc.operating").register(bp)

Resource("pevc", "updates", GPUpdate, "GP Updates", [
    F("investment_id", "Investment", type="fk", fk=Investment, required=True), F("day", "Date", type="date"),
    F("kind", type="select", choices=["Quarterly letter", "Board update", "Press release", "Capital call notice", "Annual meeting"]),
    F("title", required=True), F("sentiment", type="select", choices=["Positive", "Neutral", "Negative"]), F("read", type="bool"), F("body", type="text", list=False),
], singular="Update", order_by=GPUpdate.day.desc(), filters=["sentiment", "kind"], nav="pevc.updates").register(bp)

Resource("pevc", "documents", PEDocument, "GP Documents", [
    F("investment_id", "Investment", type="fk", fk=Investment, required=True), F("period", required=True), F("kind", type="select",
                                                                                                        choices=["Quarterly statement", "Capital account", "Financials", "K-1"]),
    F("received", type="date"), F("filename"),
], singular="Document", order_by=PEDocument.received.desc(), nav="pevc.coverage").register(bp)


@bp.route("/")
def dashboard():
    invs = positions()
    commit = sum(i.commitment or 0 for i in invs)
    paid = sum(i.invested or 0 for i in invs)
    dist = sum(i.distributions or 0 for i in invs)
    nav = sum(i.fmv or 0 for i in invs)
    by_cls = defaultdict(float)
    by_vint = defaultdict(lambda: [0.0, 0.0, 0.0])
    for i in invs:
        by_cls[f"{i.asset_class} · {i.deal_type or ''}"] += i.fmv or 0
        v = by_vint[i.vintage or 0]
        v[0] += i.invested or 0
        v[1] += i.fmv or 0
        v[2] += i.distributions or 0
    ys = sorted(by_vint)
    att = attention_items()
    upd = GPUpdate.query.order_by(GPUpdate.day.desc()).limit(6).all()
    return render("PE / VC Overview", [
        kpis([("Commitments", MS(commit), f"{len(invs)} positions", "", "#059669"), ("Paid-in", MS(paid), f"{paid / (commit or 1) * 100:.0f}% called", "", "#0ea5e9"),
              ("Unfunded", MS(commit - paid), "", "", "#f59e0b"), ("NAV", MS(nav), "", "", "#6366f1"), ("Distributions", MS(dist), f"DPI {dist / (paid or 1):.2f}x", "pos", "#10b981"),
              ("TVPI", f"{tvpi(invs):.2f}x", "net of fees", "", "#8b5cf6")]),
        row(card("NAV by strategy", chart(donut(list(by_cls), [round(v) for v in by_cls.values()]), 240)),
            card("TVPI by vintage", chart(bar_chart([str(y) for y in ys], [round((by_vint[y][1] + by_vint[y][2]) / by_vint[y][0], 2) if by_vint[y][0] else 0 for y in ys], "TVPI", money=False,
                                                    color="#059669"), 240))),
        row(card(f"Needs attention · {len(att)}", lst([(f"{i.name}", f"{k}: {d}", None, "red" if k in ("Runway", "Flag", "Call due") else "") for i, k, d in att[:8]]),
                 right=("All →", u("attention"))),
            card("Latest GP updates", lst([(x.title, f"{x.investment.name} · {x.kind} · {x.day:%b %d}", pill(x.sentiment, {'Positive': 'green', 'Negative': 'red'}.get(x.sentiment, 'gray')),
                                            "" if x.read else "blue") for x in upd]), right=("All →", u("updates")))),
    ], sub="Private equity and venture positions from the shared ledger")


@bp.route("/positions/")
def positions_page():
    invs = positions(active=request.args.get("all") != "1")
    rows = [[ilink(i), i.asset_class, i.deal_type, i.sponsor, i.vintage, M(i.commitment), M(i.invested), M(i.unfunded), M(i.fmv), M(i.distributions),
             f"{i.moic:.2f}x" if i.moic else "—", D(i.last_mark), status(i.status)] for i in invs]
    return render("Positions", [card(None, table(["Position", "Class", "Type", "Sponsor", ">Vintage", ">Commitment", ">Paid-in", ">Unfunded", ">NAV", ">Distributed",
                                                  ">TVPI", "Last mark", "Status"], rows))],
                  sub=f"{len(invs)} positions", active="pevc.positions_page",
                  actions=[("Active", u("positions_page"), "" if request.args.get("all") else "primary"), ("Include realized", u("positions_page", all=1), "primary" if request.args.get("all") else ""),
                           ("+ New position", url_for("family_office.investments_new"), "primary")])


@bp.route("/positions/<int:iid>/")
def position(iid):
    i = db.get_or_404(Investment, iid)
    if i.asset_class not in PRIVATE:
        abort(404)
    ms = i.metrics
    vals = sorted(i.valuations, key=lambda v: v.day)
    calls = sorted(i.calls, key=lambda c: c.due)
    dists = sorted(i.distribution_rows, key=lambda d: d.day)
    ups = GPUpdate.query.filter_by(investment_id=i.id).order_by(GPUpdate.day.desc()).all()
    docs = PEDocument.query.filter_by(investment_id=i.id).order_by(PEDocument.period.desc()).all()
    revs = PEReview.query.filter_by(investment_id=i.id).order_by(PEReview.quarter.desc()).all()
    ov = [kpis([("Commitment", M(i.commitment)), ("Paid-in", M(i.invested)), ("NAV", M(i.fmv)), ("Distributed", M(i.distributions)),
                ("TVPI", f"{i.moic:.2f}x" if i.moic else "—"), ("Unfunded", M(i.unfunded))]),
          row(card("NAV history", chart(line_chart([v.day.strftime("%b %y") for v in vals], {"NAV": [round(v.fmv) for v in vals]}), 220)),
              card("Details", table(["Field", "Value"], [["Sponsor", i.sponsor or "—"], ["Strategy", f"{i.asset_class} · {i.deal_type or ''}"], ["Sector", i.sector or "—"],
                                                         ["Vintage", i.vintage or "—"], ["Entity", i.entity.name if i.entity else "—"], ["Target IRR", f"{i.target_irr or 0:.0f}%"],
                                                         ["Management fee", f"{i.mgmt_fee or 0:.2f}%"], ["Attention", i.attention or "—"]], sortable=False)))]
    op = [card("Quarterly operating metrics", table(["Quarter", ">Revenue", ">EBITDA", ">Margin", ">ARR", ">Cash", ">Runway", ">Headcount"],
                                                    [[m.quarter, M(m.revenue), M(m.ebitda, color=True), f"{(m.ebitda or 0) / (m.revenue or 1) * 100:.0f}%", M(m.arr) if m.arr else "—",
                                                     M(m.cash), f"{m.runway_months:.0f} mo" if m.runway_months else "—", m.headcount] for m in reversed(ms)])),
          card("Revenue and EBITDA", chart(dict(type="bar", money=True, data=dict(labels=[m.quarter for m in ms], datasets=[dict(label="Revenue", data=[round(m.revenue or 0) for m in ms]),
                                                                                                                          dict(label="EBITDA", data=[round(m.ebitda or 0) for m in ms])])), 220))]
    cf = [row(card("Capital calls", table(["Due", ">Amount", "Status"], [[D(c.due), M(c.amount), status(c.status)] for c in calls])),
              card("Distributions", table(["Date", "Type", ">Amount"], [[D(d.day), d.kind, M(d.amount)] for d in dists])))]
    up = [card("GP updates", lst([(x.title, f"{x.kind} · {x.day:%b %d, %Y} — {x.body or ''}", pill(x.sentiment, {'Positive': 'green', 'Negative': 'red'}.get(x.sentiment, 'gray')))
                                  for x in ups])),
          card("Documents", table(["Period", "Kind", "Received", "File"], [[d.period, d.kind, D(d.received), d.filename] for d in docs])),
          card("Reviews", table(["Quarter", "Reviewer", "Decision", ">Rating", "Notes"], [[r.quarter, r.reviewer.name if r.reviewer else "—", status(r.decision), r.rating, r.notes]
                                                                                       for r in revs]))]
    return render(i.name, [tabs([("overview", "Overview", ov), ("operating", "Operating", op), ("cash", "Cash flows", cf), ("updates", "Updates & docs", up)])],
                  back=("Positions", u("positions_page")), active="pevc.positions_page", sub=f"{i.sponsor or ''} · {i.asset_class}",
                  actions=[("Edit", url_for("family_office.investments_edit", obj_id=i.id)), ("+ Metrics", u("metrics_new")), ("Review", u("review", iid=i.id), "primary")])


@bp.route("/attention/")
def attention():
    items = attention_items()
    by = defaultdict(int)
    for _, k, _d in items:
        by[k] += 1
    return render("Needs Attention", [
        kpis([(k, v) for k, v in sorted(by.items(), key=lambda x: -x[1])], cols=min(len(by), 6) or 1),
        card(None, table(["Position", "Reason", "Detail", ""], [[ilink(i), pill(k, "red" if k in ("Runway", "Flag", "Call due") else "amber"), d,
                                                              postbtn(u("clear_flag", iid=i.id), "Clear flag") if k == "Flag" else ""] for i, k, d in items], empty="Nothing needs attention.")),
    ], sub="Stale marks, falling revenue, short runway, missing statements and calls due")


@bp.route("/positions/<int:iid>/clear-flag", methods=["POST"])
@write_required
def clear_flag(iid):
    i = db.get_or_404(Investment, iid)
    audit("pevc", "clear_flag", "investment", i.id, i.attention or "")
    i.attention = None
    db.session.commit()
    flash(f"Cleared the flag on {i.name}.", "success")
    return redirect(u("attention"))


@bp.route("/operating/")
def operating():
    lq = quarters(2)
    rows = []
    for i in positions():
        cur = next((m for m in i.metrics if m.quarter == lq[1]), None)
        prev = next((m for m in i.metrics if m.quarter == lq[0]), None)
        if not cur:
            continue
        g = ((cur.revenue or 0) / prev.revenue - 1) * 100 if prev and prev.revenue else None
        rows.append([ilink(i), i.asset_class, M(cur.revenue), P(g), M(cur.ebitda, color=True), f"{(cur.ebitda or 0) / (cur.revenue or 1) * 100:.0f}%",
                     M(cur.arr) if cur.arr else "—", f"{cur.runway_months:.0f} mo" if cur.runway_months else "—", cur.headcount])
    return render("Operating Metrics", [card(f"{lq[1]} vs {lq[0]}", table(["Company", "Class", ">Revenue", ">QoQ", ">EBITDA", ">Margin", ">ARR", ">Runway", ">Headcount"], rows))],
                  actions=[("All metric rows", u("metrics_list")), ("+ Add quarter", u("metrics_new"), "primary")])


@bp.route("/updates/")
def updates():
    q = GPUpdate.query
    f = request.args.get("f", "unread")
    if f == "unread":
        q = q.filter_by(read=False)
    elif f in ("Positive", "Neutral", "Negative"):
        q = q.filter_by(sentiment=f)
    ups = q.order_by(GPUpdate.day.desc()).all()
    chips = " ".join(f'<a class="chip {"on" if f == x else ""}" href="{u("updates", f=x)}">{x.title()}</a>' for x in ["unread", "all", "Positive", "Neutral", "Negative"])
    rows = [[D(x.day), ilink(x.investment), x.kind, Markup("<b>%s</b><div class='small muted'>%s</div>") % (x.title, (x.body or "")[:160]),
             pill(x.sentiment, {'Positive': 'green', 'Negative': 'red'}.get(x.sentiment, 'gray')),
             "" if x.read else postbtn(u("mark_read", uid=x.id), "Mark read")] for x in ups]
    return render("GP Updates", [html(f'<div class="chips">{chips}</div>'), card(None, table(["Date", "Investment", "Kind", "Update", "Tone", ""], rows, empty="No updates in this view."))],
                  actions=[("post", "Mark all read", u("mark_all_read"), "", None), ("+ Log update", u("updates_new"), "primary")])


@bp.route("/updates/<int:uid>/read", methods=["POST"])
@write_required
def mark_read(uid):
    x = db.get_or_404(GPUpdate, uid)
    x.read = True
    db.session.commit()
    return redirect(request.referrer or u("updates"))


@bp.route("/updates/read-all", methods=["POST"])
@write_required
def mark_all_read():
    n = GPUpdate.query.filter_by(read=False).update({"read": True})
    audit("pevc", "read_all", "gp_update", None, f"{n} updates")
    db.session.commit()
    flash(f"Marked {n} updates read.", "success")
    return redirect(u("updates"))


@bp.route("/financials/")
def financials():
    invs = positions(active=False)
    ids = [i.id for i in invs]
    calls = CapitalCall.query.filter(CapitalCall.investment_id.in_(ids), CapitalCall.status != "Pending").all()
    dists = Distribution.query.filter(Distribution.investment_id.in_(ids)).all()
    by_y = defaultdict(lambda: [0.0, 0.0])
    for c in calls:
        by_y[c.due.year][0] -= c.amount
    for d in dists:
        by_y[d.day.year][1] += d.amount
    ys = sorted(by_y)
    cum, run = [], 0
    for y in ys:
        run += by_y[y][0] + by_y[y][1]
        cum.append(round(run))
    cfg = dict(type="bar", money=True, data=dict(labels=[str(y) for y in ys], datasets=[
        dict(label="Calls", data=[round(by_y[y][0]) for y in ys], backgroundColor="#ef4444"), dict(label="Distributions", data=[round(by_y[y][1]) for y in ys], backgroundColor="#10b981"),
        dict(label="Cumulative net", data=cum, type="line", borderColor="#6366f1")]))
    act = positions()
    paid = sum(i.invested or 0 for i in invs)
    dpi = sum(i.distributions or 0 for i in invs) / (paid or 1)
    rvpi = sum(i.fmv or 0 for i in act) / (paid or 1)
    pending = CapitalCall.query.filter(CapitalCall.investment_id.in_(ids), CapitalCall.status == "Pending").order_by(CapitalCall.due).all()
    return render("Financials", [
        kpis([("Paid-in", MS(paid)), ("DPI", f"{dpi:.2f}x"), ("RVPI", f"{rvpi:.2f}x"), ("TVPI", f"{dpi + rvpi:.2f}x"), ("Pending calls", MS(sum(c.amount for c in pending)))]),
        card("Cash flows by year (J-curve)", chart(cfg, 280)),
        card("Upcoming capital calls", table(["Investment", "Notice", "Due", ">Amount", ""], [[ilink(c.investment), D(c.notice_date), D(c.due), M(c.amount),
                                                                                             postbtn(url_for("family_office.pay_call", cid=c.id), "Fund", "btn sm green")] for c in pending])),
    ])


@bp.route("/coverage/")
def coverage():
    qs = quarters(4)
    kinds = ["Quarterly statement", "Capital account"]
    have = defaultdict(set)
    for d in PEDocument.query.filter(PEDocument.period.in_(qs)).all():
        have[(d.investment_id, d.period)].add(d.kind)
    rows = []
    miss = 0
    for i in positions():
        cells = []
        for q in qs:
            got = have[(i.id, q)]
            n = len([k for k in kinds if k in got])
            miss += len(kinds) - n
            if n == len(kinds):
                cells.append(pill("✓ complete", "green"))
            else:
                cells.append(pill(f"{n}/{len(kinds)}", "amber" if n else "red") + Markup(" ") + postbtn(u("receive_doc", iid=i.id, q=q), "Log received"))
        rows.append([ilink(i)] + cells)
    tot = len(rows) * len(qs) * len(kinds)
    return render("Document Coverage", [
        kpis([("Expected documents", tot), ("Received", tot - miss, f"{(tot - miss) / (tot or 1) * 100:.0f}%", "pos"), ("Missing", miss, "", "neg" if miss else "")]),
        card("Quarterly statement and capital account by quarter", table(["Position"] + qs, rows, sortable=False)),
    ], actions=[("All documents", u("documents_list")), ("+ Log document", u("documents_new"), "primary")])


@bp.route("/coverage/<int:iid>/<q>", methods=["POST"])
@write_required
def receive_doc(iid, q):
    i = db.get_or_404(Investment, iid)
    n = 0
    for kind in ["Quarterly statement", "Capital account"]:
        if not PEDocument.query.filter_by(investment_id=i.id, period=q, kind=kind).first():
            db.session.add(PEDocument(investment_id=i.id, period=q, kind=kind, received=date.today(), filename=f"{i.name.split(' — ')[0].replace(' ', '_')}_{q}_{kind.replace(' ', '_')}.pdf"))
            n += 1
    audit("pevc", "receive", "pe_document", i.id, f"{i.name} {q}: {n} docs")
    db.session.commit()
    flash(f"Logged {n} document(s) for {i.name} {q}.", "success")
    return redirect(u("coverage"))


@bp.route("/review/", methods=["GET", "POST"])
def review():
    q = quarters(1)[0]
    if request.method == "POST":
        if not current_user.can_write:
            abort(403)
        i = db.get_or_404(Investment, int(request.form["investment_id"]))
        r = PEReview.query.filter_by(investment_id=i.id, quarter=q).first() or PEReview(investment_id=i.id, quarter=q)
        r.reviewer_id = current_user.id
        r.decision = request.form.get("decision", "Hold")
        r.rating = int(request.form.get("rating") or 3)
        r.notes = request.form.get("notes", "")
        fmv = request.form.get("fmv")
        if fmv:
            i.fmv = float(fmv)
            i.last_mark = date.today()
            db.session.add(Valuation(investment_id=i.id, day=date.today(), fmv=i.fmv, method="GP statement", note=f"{q} review"))
        i.review_status = "Current"
        db.session.add(r)
        audit("pevc", "review", "investment", i.id, f"{q} {r.decision} rating {r.rating}")
        db.session.commit()
        flash(f"Review saved for {i.name}.", "success")
        return redirect(u("review"))
    invs = positions()
    done = {r.investment_id: r for r in PEReview.query.filter_by(quarter=q).all()}
    sel = request.args.get("iid", type=int)
    todo = [i for i in invs if i.id not in done]
    blocks = [kpis([("Quarter", q), ("Reviewed", len(done), f"of {len(invs)}", "pos"), ("Remaining", len(todo), "", "warn" if todo else "")])]
    target = db.session.get(Investment, sel) if sel else (todo[0] if todo else None)
    if target:
        ex = done.get(target.id)
        blocks.append(card(f"Review: {target.name}", [
            html(f"<div class='small muted' style='margin-bottom:8px'>NAV {target.fmv or 0:,.0f} · TVPI {target.moic or 0:.2f}x · last mark {D(target.last_mark)}</div>"),
            form(u("review"), [("investment_id", "", "hidden", target.id),
                               ("decision", "Decision", "select", [(x, x, ex and ex.decision == x) for x in ["Hold", "Watch", "Add", "Exit"]]),
                               ("rating", "Rating (1–5)", "number", ex.rating if ex else 3), ("fmv", "New NAV mark (optional)", "number", None),
                               ("notes", "Notes", "textarea", ex.notes if ex else "")], submit="Save review")], flush=False))
    blocks.append(row(card("To review", table(["Position", ">NAV", ""], [[ilink(i), M(i.fmv), link("Review →", u("review", iid=i.id))] for i in todo], empty="All reviewed.")),
                      card("Reviewed", table(["Position", "Decision", ">Rating", "Reviewer"], [[ilink(r.investment), status(r.decision), r.rating, r.reviewer.name if r.reviewer else "—"]
                                                                                             for r in done.values()]))))
    return render("Quarterly Review", blocks, sub="Rate each position, record a decision, and optionally book a new mark")

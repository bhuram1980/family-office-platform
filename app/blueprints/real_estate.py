"""Real Estate app: the same property, loan and metro rows the Family Office ledger uses, seen as an operator."""
import re
from collections import defaultdict
from datetime import date, timedelta

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import Entity, Loan, Metro, Property, PropertyMonth, REIssue
from ..pages import (D, M, MS, P, b, bar_chart, bars, card, chart, donut, form, html, kpis, line_chart, link, lst, note, pill, render, row,
                     status, table, tabs)
from ..services import re_rules
from ..services import settings as st
from ..services.audit import audit
from .common import make_bp, write_required

bp = make_bp("real-estate", "real_estate")


def u(ep, **kw):
    return url_for(f"real_estate.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return html(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                f'<button class="{cls}">{label}</button></form>')["html"]


def plink(p):
    return link(p.name, u("property", pid=p.id), "tk")


def live():
    return Property.query.filter(Property.status != "Sold").all()


SEV = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


Resource("real-estate", "metros", Metro, "Metros", [
    F("name", required=True), F("state"), F("pop_yoy", "Population YoY %", type="float"), F("emp_yoy", "Jobs YoY %", type="float"),
    F("hpi_yoy", "Home prices YoY %", type="float"), F("rent_yoy", "Rents YoY %", type="float"), F("permits_yoy", "Permits YoY %", type="float"),
    F("score", "Score", type="int"),
], singular="Metro", order_by=Metro.score.desc(), nav="real_estate.markets").register(bp)

Resource("real-estate", "loans", Loan, "Property Loans", [
    F("name", required=True), F("property_id", "Property", type="fk", fk=Property), F("lender"), F("principal", type="money", list=False),
    F("balance", type="money"), F("rate", "Rate %", type="float"), F("rate_type", type="select", choices=["Fixed", "Floating"]),
    F("originated", type="date", list=False), F("maturity", type="date"), F("annual_debt_service", "Annual debt service", type="money"),
    F("dscr_covenant", "DSCR covenant", type="float"), F("status", type="select", choices=["Current", "Watch", "Default", "Paid off"]),
    F("kind", type="select", choices=["Mortgage"], list=False, default="Mortgage"), F("direction", type="select", choices=["payable"], list=False, default="payable"),
], singular="Loan", order_by=Loan.maturity, query=lambda: Loan.query.filter(Loan.property_id.isnot(None)), nav="real_estate.debt").register(bp)

Resource("real-estate", "property-records", Property, "Properties", [
    F("name", required=True), F("entity_id", "Owner", type="fk", fk=Entity),
    F("kind", type="select", choices=["Multifamily", "Industrial", "Retail", "Office", "Self-storage", "Hospitality", "Land"]),
    F("address", list=False), F("city"), F("state"), F("metro", list=False), F("units", type="int"), F("sqft", "Sq ft", type="int", list=False),
    F("purchase_price", type="money", list=False), F("acquired", type="date", list=False), F("fmv", "FMV", type="money"),
    F("ownership_pct", "Owned %", type="float", list=False), F("noi_t12", "NOI (T-12)", type="money"), F("revenue_t12", "Revenue (T-12)", type="money", list=False),
    F("opex_t12", "Opex (T-12)", type="money", list=False), F("occupancy", "Occupancy %", type="float"), F("capex_budget", type="money", list=False),
    F("cap_rate_uw", "UW cap rate %", type="float", list=False), F("noi_uw", "UW NOI", type="money", list=False),
    F("status", type="select", choices=["Operating", "Development", "Under contract", "Sold"]), F("manager", list=False),
], singular="Property", order_by=Property.fmv.desc(), nav="real_estate.properties", row_link=lambda o: url_for("real_estate.property", pid=o.id)).register(bp)


def _maturities(months=24):
    end = date.today() + timedelta(days=months * 30)
    return Loan.query.filter(Loan.property_id.isnot(None), Loan.maturity <= end).order_by(Loan.maturity).all()


@bp.route("/")
def dashboard():
    props = live()
    fmv = sum(p.fmv or 0 for p in props)
    debt = sum(p.debt for p in props)
    noi = sum(p.noi_t12 or 0 for p in props)
    ds = sum(p.debt_service for p in props)
    units = sum(p.units or 0 for p in props)
    issues = sorted(REIssue.query.filter_by(status="Open").all(), key=lambda i: SEV.get(i.severity, 3))
    metros = Metro.query.order_by(Metro.score.desc()).all()
    owned = defaultdict(float)
    for p in props:
        owned[p.metro or p.city] += p.fmv or 0
    by_kind = defaultdict(float)
    for p in props:
        by_kind[p.kind] += p.fmv or 0
    start = (date.today().replace(day=1) - timedelta(days=365)).replace(day=1)
    by_m = defaultdict(float)
    for m in PropertyMonth.query.filter(PropertyMonth.month >= start).all():
        by_m[m.month] += m.noi or 0
    ks = sorted(by_m)
    mat = _maturities()
    dot = {"HIGH": "red", "MEDIUM": "", "LOW": "blue"}
    return render("Real Estate", [
        kpis([("Fair market value", MS(fmv), f"{len(props)} properties", "", "#16a34a"), ("Equity", MS(fmv - debt), f"{(fmv - debt) / (fmv or 1) * 100:.0f}% of value", "pos", "#6366f1"),
              ("NOI (T-12)", MS(noi), f"cap rate {noi / (fmv or 1) * 100:.2f}%", "", "#0ea5e9"), ("Debt", MS(debt), f"LTV {debt / (fmv or 1) * 100:.0f}%", "", "#ef4444"),
              ("DSCR", f"{noi / ds:.2f}x" if ds else "—", "portfolio", "", "#f59e0b"), ("Units", f"{units:,}", f"{sum(p.sqft or 0 for p in props) / 1e6:.1f}M sq ft", "", "#8b5cf6")]),
        row(card("Monthly NOI", chart(line_chart([k.strftime("%b %y") for k in ks], {"NOI": [round(by_m[k]) for k in ks]}, fill=True), 230)),
            card("Value by type", chart(donut(list(by_kind), [round(v) for v in by_kind.values()]), 230))),
        row(card(f"Issue queue · {len(issues)} open", lst([(f"{i.property.name}: {i.title}", i.detail, pill(i.severity, {'HIGH': 'red', 'MEDIUM': 'amber', 'LOW': 'blue'}[i.severity]),
                                                          dot.get(i.severity)) for i in issues[:8]], empty="No open issues."),
                 right=("All issues →", u("issues"))),
            card("Debt maturities (24 months)", table(["Loan", "Property", ">Balance", ">Rate", "Matures"],
                                                      [[link(l.name, u("loans_edit", obj_id=l.id)), plink(l.property), M(l.balance), f"{l.rate or 0:.2f}%", D(l.maturity)] for l in mat],
                                                      empty="Nothing matures in the next 24 months."), right=("Debt →", u("debt")))),
        card("Market Watch", table(["Metro", ">Score", ">Jobs", ">Population", ">Rents", ">Home prices", ">Permits", ">Our FMV"],
                                   [[m.name, b(str(m.score)), P(m.emp_yoy), P(m.pop_yoy), P(m.rent_yoy), P(m.hpi_yoy), P(m.permits_yoy, color=False), M(owned.get(m.name, 0))]
                                    for m in metros[:8]]), right=("All markets →", u("markets"))),
    ], sub=f"As of {date.today():%B %d, %Y}", actions=[("post", "Run checks", u("run_checks"), "", None), ("+ Add property", u("property_records_new"), "primary")])


@bp.route("/properties/")
def properties():
    props = Property.query.order_by(Property.fmv.desc()).all()
    kinds = sorted({p.kind for p in props if p.kind})
    k = request.args.get("type")
    if k:
        props = [p for p in props if p.kind == k]
    chips = " ".join(f'<a class="chip {"on" if (k or "") == x else ""}" href="{u("properties", type=x) if x else u("properties")}">{x or "All"}</a>' for x in [""] + kinds)
    open_by = defaultdict(int)
    for i in REIssue.query.filter_by(status="Open").all():
        open_by[i.property_id] += 1
    return render("Properties", [
        html(f'<div class="chips">{chips}</div>'),
        card(None, table(["Property", "Type", "Location", ">Units", ">FMV", ">Equity", ">NOI T-12", ">Cap rate", ">DSCR", ">Occupancy", ">Issues", "Status"],
                         [[plink(p), p.kind, f"{p.city}, {p.state}", p.units or "—", M(p.fmv), M(p.equity), M(p.noi_t12), f"{p.cap_rate:.2f}%",
                           f"{p.dscr:.2f}x" if p.dscr else "—", f"{p.occupancy or 0:.1f}%", pill(str(open_by[p.id]), "red") if open_by[p.id] else "—", status(p.status)] for p in props])),
    ], sub=f"{len(props)} properties", actions=[("Export CSV", u("property_records_export")), ("+ Add property", u("property_records_new"), "primary")])


@bp.route("/properties/<int:pid>/")
def property(pid):
    p = db.get_or_404(Property, pid)
    ms = sorted(p.months, key=lambda m: m.month)[-24:]
    labels = [m.month.strftime("%b %y") for m in ms]
    issues = REIssue.query.filter_by(property_id=p.id).order_by(REIssue.status.desc()).all()
    var = ((p.noi_t12 or 0) - (p.noi_uw or 0)) / p.noi_uw * 100 if p.noi_uw else None
    ov = [
        kpis([("FMV", M(p.fmv)), ("Debt", M(p.debt)), ("Equity", M(p.equity)), ("NOI T-12", M(p.noi_t12), P(var) if var is not None else "", ""),
              ("DSCR", f"{p.dscr:.2f}x" if p.dscr else "—"), ("Occupancy", f"{p.occupancy or 0:.1f}%")]),
        card("Revenue, opex and NOI", chart(line_chart(labels, {"Revenue": [round(m.revenue or 0) for m in ms], "Opex": [round(m.opex or 0) for m in ms],
                                                                 "NOI": [round(m.noi or 0) for m in ms]}), 260)),
        row(card("Facts", table(["Field", "Value"], [["Type", p.kind], ["Address", f"{p.address or ''}, {p.city}, {p.state}"], ["Metro", p.metro or "—"],
                                                     ["Owner", p.entity.name if p.entity else "—"], ["Ownership", f"{p.ownership_pct or 100:.0f}%"],
                                                     ["Units / sq ft", f"{p.units or '—'} / {p.sqft or 0:,}"], ["Acquired", D(p.acquired)],
                                                     ["Purchase price", M(p.purchase_price)], ["Manager", p.manager or "—"]], sortable=False)),
            card("Underwriting", table(["Measure", ">Underwritten", ">Actual"], [["NOI", M(p.noi_uw), M(p.noi_t12)], ["Cap rate", f"{p.cap_rate_uw or 0:.2f}%", f"{p.cap_rate:.2f}%"],
                                                                                 ["Capex budget", M(p.capex_budget), "—"]], sortable=False))),
    ]
    debt = [card("Loans", table(["Loan", "Lender", ">Balance", ">Rate", "Type", "Matures", ">Debt service", ">Covenant", "Status"],
                                [[link(l.name, u("loans_edit", obj_id=l.id)), l.lender, M(l.balance), f"{l.rate or 0:.2f}%", l.rate_type, D(l.maturity),
                                  M(l.annual_debt_service), f"{l.dscr_covenant:.2f}x" if l.dscr_covenant else "—", status(l.status)] for l in p.loans], empty="Unlevered."))]
    fin = [card("Monthly P&L", table(["Month", ">Revenue", ">Opex", ">NOI", ">Margin", ">Occupancy", "Reviewed"],
                                     [[m.month.strftime("%B %Y"), M(m.revenue), M(m.opex), M(m.noi), f"{(m.noi or 0) / (m.revenue or 1) * 100:.0f}%", f"{m.occupancy or 0:.1f}%",
                                       status("Done") if m.reviewed else postbtn(u("review_month", mid=m.id), "Mark reviewed")] for m in reversed(ms)], max_height=480))]
    iss = [card("Issues", table(["Severity", "Rule", "Issue", "Detail", "Status", ""],
                                [[pill(i.severity, {'HIGH': 'red', 'MEDIUM': 'amber', 'LOW': 'blue'}.get(i.severity, 'gray')), i.rule, i.title, i.detail, status(i.status),
                                  _issue_btns(i)] for i in issues], empty="No issues."))]
    return render(p.name, [tabs([("overview", "Overview", ov), ("financials", "Financials", fin), ("debt", f"Debt ({len(p.loans)})", debt),
                                 ("issues", f"Issues ({len([i for i in issues if i.status == 'Open'])})", iss)])],
                  sub=f"{p.kind} · {p.city}, {p.state}", back=("Properties", u("properties")), active="real_estate.properties",
                  actions=[("Edit", u("property_records_edit", obj_id=p.id)), ("+ Add month", u("add_month", pid=p.id), "primary")])


@bp.route("/properties/<int:pid>/month", methods=["GET", "POST"])
def add_month(pid):
    p = db.get_or_404(Property, pid)
    last = max((m.month for m in p.months), default=date.today().replace(day=1) - timedelta(days=31))
    nxt = (last + timedelta(days=32)).replace(day=1)
    if request.method == "POST":
        if not current_user.can_write:
            abort(403)
        mo = date.fromisoformat(request.form["month"] + "-01")
        rev = float(request.form.get("revenue") or 0)
        opex = float(request.form.get("opex") or 0)
        m = PropertyMonth.query.filter_by(property_id=p.id, month=mo).first() or PropertyMonth(property_id=p.id, month=mo)
        m.revenue, m.opex, m.noi = rev, opex, rev - opex
        m.occupancy = float(request.form.get("occupancy") or 0) or None
        db.session.add(m)
        db.session.flush()
        recent = sorted(p.months, key=lambda x: x.month)[-12:]
        p.revenue_t12 = sum(x.revenue or 0 for x in recent)
        p.opex_t12 = sum(x.opex or 0 for x in recent)
        p.noi_t12 = sum(x.noi or 0 for x in recent)
        if m.occupancy:
            p.occupancy = m.occupancy
        audit("real-estate", "create", "property_month", m.id, f"{p.name} {mo:%Y-%m}")
        db.session.commit()
        flash(f"{p.name} {mo:%B %Y} saved; T-12 updated.", "success")
        return redirect(u("property", pid=p.id, tab="financials"))
    return render(f"Add month · {p.name}", [card(None, form(u("add_month", pid=p.id), [("month", "Month (YYYY-MM)", "month", nxt.strftime("%Y-%m")),
                                                                                     ("revenue", "Revenue", "number", None), ("opex", "Operating expenses", "number", None),
                                                                                     ("occupancy", "Occupancy %", "number", p.occupancy)]), flush=False)],
                  back=(p.name, u("property", pid=p.id)), active="real_estate.properties")


@bp.route("/months/<int:mid>/review", methods=["POST"])
@write_required
def review_month(mid):
    m = db.get_or_404(PropertyMonth, mid)
    m.reviewed = True
    audit("real-estate", "review", "property_month", m.id, f"{m.property.name} {m.month:%Y-%m}")
    db.session.commit()
    return redirect(u("property", pid=m.property_id, tab="financials"))


def _issue_btns(i):
    if i.status != "Open":
        return postbtn(u("issue_action", iid=i.id, action="reopen"), "Reopen")
    return postbtn(u("issue_action", iid=i.id, action="resolve"), "Resolve", "btn sm green") + " " + postbtn(u("issue_action", iid=i.id, action="snooze"), "Snooze")


@bp.route("/issues/")
def issues():
    st_ = request.args.get("status", "Open")
    q = REIssue.query
    if st_ != "All":
        q = q.filter_by(status=st_)
    items = sorted(q.all(), key=lambda i: (SEV.get(i.severity, 3), i.property.name))
    counts = defaultdict(int)
    for i in REIssue.query.filter_by(status="Open").all():
        counts[i.severity] += 1
    chips = " ".join(f'<a class="chip {"on" if st_ == x else ""}" href="{u("issues", status=x)}">{x}</a>' for x in ["Open", "Snoozed", "Resolved", "All"])
    return render("Issue Queue", [
        kpis([("High", counts["HIGH"], "", "neg" if counts["HIGH"] else "", "#ef4444"), ("Medium", counts["MEDIUM"], "", "warn" if counts["MEDIUM"] else "", "#f59e0b"),
              ("Low", counts["LOW"], "", "", "#0ea5e9")]),
        html(f'<div class="chips">{chips}</div>'),
        card(None, table(["Severity", "Property", "Rule", "Issue", "Detail", "Status", ""],
                         [[pill(i.severity, {'HIGH': 'red', 'MEDIUM': 'amber', 'LOW': 'blue'}.get(i.severity, 'gray')), plink(i.property), i.rule, i.title, i.detail,
                           status(i.status), _issue_btns(i)] for i in items], empty="Nothing in this view.")),
    ], sub="Generated from the thresholds in Settings", active="real_estate.dashboard", actions=[("post", "Run checks", u("run_checks"), "primary", None)])


@bp.route("/issues/<int:iid>/<action>", methods=["POST"])
@write_required
def issue_action(iid, action):
    i = db.get_or_404(REIssue, iid)
    i.status = {"resolve": "Resolved", "snooze": "Snoozed", "reopen": "Open"}.get(action) or abort(400)
    audit("real-estate", action, "re_issue", i.id, f"{i.property.name}: {i.title}")
    db.session.commit()
    return redirect(request.referrer or u("issues"))


@bp.route("/run-checks", methods=["POST"])
@write_required
def run_checks():
    n = re_rules.run_checks()
    audit("real-estate", "run", "re_rules", None, f"{n} open issues")
    db.session.commit()
    flash(f"Checks complete: {n} open issue(s).", "success")
    return redirect(request.referrer or u("dashboard"))


@bp.route("/debt/")
def debt():
    loans = Loan.query.filter(Loan.property_id.isnot(None)).order_by(Loan.maturity).all()
    by_year = defaultdict(float)
    for l in loans:
        if l.maturity:
            by_year[l.maturity.year] += l.balance or 0
    ys = sorted(by_year)
    tot = sum(l.balance or 0 for l in loans)
    fl = sum(l.balance or 0 for l in loans if l.rate_type == "Floating")
    wavg = sum((l.rate or 0) * (l.balance or 0) for l in loans) / (tot or 1)
    shock = float(request.args.get("shock", 200))
    rows = []
    for l in loans:
        p = l.property
        extra = (l.balance or 0) * shock / 10000 if l.rate_type == "Floating" else 0
        ds2 = (l.annual_debt_service or 0) + extra
        rows.append([link(l.name, u("loans_edit", obj_id=l.id)), plink(p), l.lender, M(l.balance), f"{l.rate or 0:.2f}%", l.rate_type, D(l.maturity),
                     f"{p.dscr:.2f}x" if p.dscr else "—", f"{(p.noi_t12 or 0) / ds2:.2f}x" if ds2 else "—", status(l.status)])
    return render("Debt", [
        kpis([("Property debt", MS(tot), f"{len(loans)} loans", "", "#ef4444"), ("Weighted rate", f"{wavg:.2f}%", "", "", "#f59e0b"),
              ("Floating", f"{fl / (tot or 1) * 100:.0f}%", MS(fl), "warn" if fl else "", "#8b5cf6"),
              ("Annual debt service", MS(sum(l.annual_debt_service or 0 for l in loans)), "", "", "#6366f1")]),
        card("Maturity ladder", chart(bar_chart([str(y) for y in ys], [round(by_year[y]) for y in ys], "Balance maturing", color="#ef4444"), 220)),
        card(f"Loans · DSCR after a +{shock:.0f} bp shock on floating debt", table(["Loan", "Property", "Lender", ">Balance", ">Rate", "Type", "Matures", ">DSCR", ">Shocked DSCR", "Status"], rows),
             right=None),
    ], actions=[(f"+{x} bp", u("debt", shock=x), "primary" if x == shock else "") for x in (100, 200, 300)] + [("+ New loan", u("loans_new"), "primary")])


@bp.route("/markets/")
def markets():
    metros = Metro.query.order_by(Metro.score.desc()).all()
    owned = defaultdict(lambda: [0, 0.0])
    for p in live():
        owned[p.metro or p.city][0] += 1
        owned[p.metro or p.city][1] += p.fmv or 0
    return render("Market Watch", [
        note("Score blends job growth, population growth, rent growth and supply (permits). Edit a metro to update its indicators."),
        card("Score by metro", chart(bar_chart([m.name for m in metros], [m.score for m in metros], "Score", money=False, color="#16a34a"), 240)),
        card("Metros", table(["Metro", "State", ">Score", ">Jobs YoY", ">Population YoY", ">Rents YoY", ">Home prices YoY", ">Permits YoY", ">Our properties", ">Our FMV", ""],
                             [[b(m.name), m.state, m.score, P(m.emp_yoy), P(m.pop_yoy), P(m.rent_yoy), P(m.hpi_yoy), P(m.permits_yoy, color=False), owned[m.name][0],
                               M(owned[m.name][1]), link("Edit", u("metros_edit", obj_id=m.id))] for m in metros])),
    ], actions=[("+ Add metro", u("metros_new"), "primary")])


# ---------------------------------------------------------------- portfolio Q&A (rule-based, no external model)
SUGGEST = ["Which properties have DSCR below 1.25?", "What matures in the next 12 months?", "Top 5 by NOI", "Lowest occupancy",
           "Total equity by type", "How much floating-rate debt do we have?", "Show issues for Cedar"]


def answer(q):
    ql = q.lower()
    props = live()
    num = re.search(r"(\d+(?:\.\d+)?)", ql)
    if "dscr" in ql:
        lim = float(num.group(1)) if num else 1.25
        hits = [p for p in props if p.dscr and p.dscr < lim]
        return f"{len(hits)} properties are below {lim:.2f}x DSCR.", table(["Property", ">DSCR", ">NOI", ">Debt service"],
                                                                           [[plink(p), f"{p.dscr:.2f}x", M(p.noi_t12), M(p.debt_service)] for p in hits])
    if "matur" in ql:
        months = int(num.group(1)) if num else 12
        ls = _maturities(months)
        return f"{len(ls)} loans, ${sum(l.balance or 0 for l in ls):,.0f}, mature in the next {months} months.", table(
            ["Loan", "Property", ">Balance", "Matures"], [[l.name, plink(l.property), M(l.balance), D(l.maturity)] for l in ls])
    if "occupan" in ql:
        s = sorted(props, key=lambda p: p.occupancy or 0)[: int(num.group(1)) if num else 5]
        return "Lowest occupancy:", table(["Property", ">Occupancy"], [[plink(p), f"{p.occupancy or 0:.1f}%"] for p in s])
    if "noi" in ql or "top" in ql:
        n = int(num.group(1)) if num else 5
        s = sorted(props, key=lambda p: -(p.noi_t12 or 0))[:n]
        return f"Top {n} by T-12 NOI:", table(["Property", ">NOI", ">Cap rate"], [[plink(p), M(p.noi_t12), f"{p.cap_rate:.2f}%"] for p in s])
    if "equity" in ql or "by type" in ql:
        by = defaultdict(float)
        for p in props:
            by[p.kind] += p.equity
        return f"Total equity ${sum(by.values()):,.0f}.", bars(sorted(by.items(), key=lambda x: -x[1]), "#16a34a")
    if "floating" in ql or "variable" in ql:
        ls = [l for l in Loan.query.filter(Loan.property_id.isnot(None)).all() if l.rate_type == "Floating"]
        return f"${sum(l.balance or 0 for l in ls):,.0f} of floating-rate debt across {len(ls)} loans.", table(
            ["Loan", "Property", ">Balance", ">Rate"], [[l.name, plink(l.property), M(l.balance), f"{l.rate or 0:.2f}%"] for l in ls])
    if "issue" in ql:
        words = [w for w in re.findall(r"[a-z]{4,}", ql) if w not in ("show", "issues", "issue", "with", "open", "what", "which")]
        its = [i for i in REIssue.query.filter_by(status="Open").all() if not words or any(w in i.property.name.lower() for w in words)]
        return f"{len(its)} open issue(s).", table(["Property", "Severity", "Issue"], [[plink(i.property), i.severity, i.title] for i in its])
    for p in props:
        if p.name.lower().split()[0] in ql:
            return (f"{p.name}: FMV ${p.fmv or 0:,.0f}, debt ${p.debt:,.0f}, NOI ${p.noi_t12 or 0:,.0f}, DSCR {p.dscr or 0:.2f}x, occupancy {p.occupancy or 0:.1f}%.",
                    link("Open property →", u("property", pid=p.id)))
    return "I can answer questions about DSCR, maturities, occupancy, NOI rankings, equity by type, floating debt, issues, or a property by name.", None


@bp.route("/ai/", methods=["GET", "POST"])
def ai():
    q = (request.values.get("q") or "").strip()
    blocks = [card(None, html(f'<form method="get" style="display:flex;gap:8px"><input class="inp" name="q" value="{q}" placeholder="Ask about the portfolio…" style="flex:1">'
                              f'<button class="btn primary">Ask</button></form><div class="chips" style="margin-top:10px">'
                              + "".join(f'<a class="chip" href="{u("ai", q=s)}">{s}</a>' for s in SUGGEST) + "</div>"), flush=False)]
    if q:
        text, body = answer(q)
        blocks.append(card(q, [note(text)] + ([body] if body else []), flush=False))
    return render("Portfolio Q&A", blocks, sub="Answers are computed directly from the property, loan and issue tables")


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    r = st.handle("real-estate", re_rules.KEYS)
    if r:
        return r
    return render("Settings", [card("Issue thresholds", form(u("settings"), st.form_fields("real-estate", re_rules.KEYS)), flush=False,
                                    sub="Saved thresholds apply the next time checks run."),
                               card("Data", html(f'<a class="btn" href="{u("property_records_list")}">Property records</a> <a class="btn" href="{u("loans_list")}">Loans</a> '
                                                 f'<a class="btn" href="{u("metros_list")}">Metros</a>'), flush=False)])

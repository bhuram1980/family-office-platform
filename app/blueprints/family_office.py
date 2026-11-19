from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from markupsafe import escape

from ..crud import Field, Resource
from ..extensions import db
from ..models import (ASSET_CLASSES, BankAccount, Bill, BrokerageAccount, CapitalCall, CashTxn, CloseTask, ComplianceItem,
                      Contract, Distribution, Entity, EstimatedTax, Exchange1031, FamilyObligation, InsurancePolicy, Investment,
                      K1, LegalDocument, LegalMatter, Loan, PersonalAsset, Property, PropertyMonth, RecurringCash, ReportRun,
                      SharedExpense, TaxFiling, TreasuryHolding, Valuation, Vendor, Wire, User)
from ..pages import (D, M, MS, P, b, bar_chart, bars, card, chart, donut, form, kpis, line_chart, link, lst, note, pill, render,
                     row, small, status, table, tabs, html)
from ..services import fo as fos
from ..services import portfolio as pf
from ..services.audit import audit
from .common import admin_required, make_bp, write_required

bp = make_bp("family-office", "family_office")
F = Field


def ENT():
    return F("entity_id", "Entity", type="fk", fk=Entity)


def u(ep, **kw):
    return url_for(f"family_office.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm"):
    return html(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}"><button class="{cls}">{label}</button></form>')["html"]


# ======================================================================= summaries
def _inv_summary():
    invs = fos.active_investments()
    inv = sum(i.invested or 0 for i in invs)
    fmv = sum(i.fmv or 0 for i in invs)
    dist = sum(i.distributions or 0 for i in invs)
    return [kpis([("Active investments", len(invs), f"{len(set(i.asset_class for i in invs))} asset classes", "", "#6366f1"),
                  ("Invested", MS(inv), "paid-in capital", "", "#0ea5e9"), ("Fair market value", MS(fmv), "latest marks", "", "#10b981"),
                  ("Distributions", MS(dist), "since inception", "", "#f59e0b"),
                  ("Multiple", f"{(fmv + dist) / inv:.2f}x" if inv else "—", "(FMV + dist) / invested", "", "#8b5cf6")])]


def _dist_summary():
    rows = Distribution.query.all()
    by_m = defaultdict(float)
    for d in rows:
        by_m[d.day.strftime("%Y-%m")] += d.amount
    months = sorted(by_m)[-12:]
    ytd = sum(d.amount for d in rows if d.day.year == date.today().year)
    untied = [d for d in rows if not d.tied_out]
    return [kpis([("YTD", MS(ytd), "received this year", "pos", "#10b981"), ("Trailing 12 months", MS(sum(by_m[m] for m in months)), "", "", "#6366f1"),
                  ("Not tied out", len(untied), f"{_ms(sum(d.amount for d in untied))} to match to bank", "warn" if untied else "", "#f59e0b")]),
            card("Distribution trend", chart(bar_chart(months, [round(by_m[m]) for m in months], "Distributions", color="#059669"), 200))]


def _ms(v):
    from ..filters import money_short
    return money_short(v)


def _val_summary():
    invs = Investment.query.filter(Investment.asset_class.in_(["Private Equity", "Venture Capital", "Real Estate", "Private Credit"]), Investment.status == "Active").all()
    stale = [i for i in invs if not i.last_mark or (date.today() - i.last_mark).days > 120]
    return [kpis([("Marked positions", len(invs), "non-marketable", "", "#6366f1"), ("Stale marks (>120d)", len(stale), "need a new valuation", "neg" if stale else "", "#ef4444"),
                  ("Total FMV", MS(sum(i.fmv or 0 for i in invs)), "latest marks", "", "#10b981")]),
            card("Stale marks", table(["Investment", "Class", "Last mark", ">Days", ">FMV"],
                                      [[link(i.name, url_for("family_office.investments_edit", obj_id=i.id)), i.asset_class, D(i.last_mark),
                                        (date.today() - i.last_mark).days if i.last_mark else "—", M(i.fmv)] for i in stale], max_height=260))]


def _loan_summary():
    loans = Loan.query.all()
    pay = [l for l in loans if l.direction == "payable"]
    rec = [l for l in loans if l.direction == "receivable" and l.kind != "Intercompany"]
    wavg = sum((l.rate or 0) * (l.balance or 0) for l in pay) / (sum(l.balance or 0 for l in pay) or 1)
    soon = [l for l in loans if l.maturity and l.maturity <= date.today() + timedelta(days=365)]
    return [kpis([("Debt outstanding", MS(sum(l.balance or 0 for l in pay)), f"{len(pay)} loans", "", "#ef4444"), ("Weighted rate", f"{wavg:.2f}%", "on payables", "", "#f59e0b"),
                  ("Notes receivable", MS(sum(l.balance or 0 for l in rec)), f"{len(rec)} notes", "pos", "#10b981"),
                  ("Maturing ≤ 12 months", len(soon), _ms(sum(l.balance or 0 for l in soon)), "warn" if soon else "", "#8b5cf6")])]


def _shared_summary():
    alloc = defaultdict(float)
    for s in SharedExpense.query.filter_by(settled=False).all():
        for n, p in s.split():
            alloc[n] += (s.total or 0) * p / 100
    return [card("Unsettled allocation by entity", bars(sorted(alloc.items(), key=lambda x: -x[1]), "#8b5cf6"), sub="What each entity owes Holdings for shared costs")]


def _cash_summary():
    accts = BankAccount.query.all()
    by_kind = defaultdict(float)
    for a in accts:
        by_kind[a.kind] += a.balance or 0
    low = [a for a in accts if (a.balance or 0) < (a.min_balance or 0)]
    out = [kpis([("Total cash", MS(sum(by_kind.values())), f"{len(accts)} accounts", "", "#10b981")] + [(k, MS(v)) for k, v in by_kind.items()])]
    if low:
        out.append(note(f"{len(low)} account(s) below minimum balance: " + ", ".join(a.name for a in low), "amber"))
    return out


def _treasury_summary():
    t = TreasuryHolding.query.all()
    face = sum(x.face or 0 for x in t)
    wy = sum((x.yld or 0) * (x.face or 0) for x in t) / (face or 1)
    return [kpis([("Face value", MS(face), f"{len(t)} bills", "", "#6366f1"), ("Weighted yield", f"{wy:.2f}%", "", "pos", "#10b981"),
                  ("Next maturity", D(min((x.maturity for x in t), default=None)), "", "", "#f59e0b")])]


def _bills_summary():
    bills = Bill.query.filter(Bill.status != "Paid").all()
    today = date.today()
    od = [x for x in bills if x.due < today]
    wk = [x for x in bills if today <= x.due <= today + timedelta(days=7)]
    return [kpis([("Open payables", MS(sum(x.amount for x in bills)), f"{len(bills)} bills", "", "#6366f1"),
                  ("Overdue", len(od), _ms(sum(x.amount for x in od)), "neg" if od else "", "#ef4444"),
                  ("Due in 7 days", len(wk), _ms(sum(x.amount for x in wk)), "warn" if wk else "", "#f59e0b"),
                  ("Approved, unpaid", len([x for x in bills if x.status == "Approved"]), "ready to pay", "", "#10b981")])]


def _k1_summary():
    ks = K1.query.all()
    rec = [k for k in ks if k.received]
    late = [k for k in ks if not k.received and k.expected and k.expected < date.today()]
    return [kpis([("Expected", len(ks), "", "", "#6366f1"), ("Received", len(rec), f"{len(rec) / (len(ks) or 1) * 100:.0f}%", "pos", "#10b981"),
                  ("Late", len(late), "past expected date", "neg" if late else "", "#ef4444")])]


# ======================================================================= resources
Resource("family-office", "investments", Investment, "Investments", [
    F("name", required=True), ENT(), F("asset_class", "Asset class", type="select", choices=ASSET_CLASSES, required=True),
    F("deal_type", "Type", type="select", choices=["Fund", "Co-Invest", "Direct", "Buyout", "Growth", "Early Stage", "Separate account"]),
    F("sponsor", list=False), F("sector"), F("vintage", type="int"), F("commitment", type="money", list=False),
    F("invested", type="money"), F("fmv", "FMV", type="money"), F("distributions", type="money"),
    F("status", type="select", choices=["Active", "Sold", "Written off"]), F("marketable", type="bool", list=False),
    F("city", list=False), F("state", list=False), F("lat", "Latitude", type="float", list=False), F("lon", "Longitude", type="float", list=False),
    F("target_irr", "Target IRR %", type="float", list=False), F("target_moic", "Target MOIC", type="float", list=False),
    F("hold_years", type="float", list=False), F("pref_return", "Pref %", type="float", list=False), F("promote", "Promote %", type="float", list=False),
    F("mgmt_fee", "Mgmt fee %", type="float", list=False), F("last_mark", type="date", list=False), F("sold_on", type="date", list=False),
    F("attention", list=False), F("notes", type="text", list=False),
], singular="Investment", order_by=Investment.fmv.desc(), filters=["asset_class", "status"], search=["name", "sponsor", "sector"],
    summary=_inv_summary, extra_actions=[("Map", "family_office.investment_map")]).register(bp)

Resource("family-office", "distributions", Distribution, "Distributions", [
    F("investment_id", "Investment", type="fk", fk=Investment, required=True), F("day", "Date", type="date", required=True),
    F("amount", type="money", required=True), F("kind", type="select", choices=["Income", "Return of capital", "Gain"]), F("tied_out", "Tied out", type="bool"),
], singular="Distribution", order_by=Distribution.day.desc(), filters=["kind"], summary=_dist_summary).register(bp)

Resource("family-office", "valuations", Valuation, "Valuation", [
    F("investment_id", "Investment", type="fk", fk=Investment, required=True), F("day", "As of", type="date", required=True),
    F("fmv", "FMV", type="money", required=True),
    F("method", type="select", choices=["GP statement", "Mark-to-model", "Recent round", "Appraisal", "Broker opinion"]), F("note"),
], singular="Valuation", order_by=Valuation.day.desc(), filters=["method"], summary=_val_summary).register(bp)

Resource("family-office", "loans", Loan, "Loans", [
    F("name", required=True), F("kind", type="select", choices=["Mortgage", "Note receivable", "Note payable", "Line of credit", "Intercompany"]),
    F("direction", type="select", choices=["payable", "receivable"]), F("lender"), F("borrower", list=False), ENT(),
    F("property_id", "Property", type="fk", fk=Property, list=False), F("principal", type="money", list=False), F("balance", type="money"),
    F("rate", "Rate %", type="float"), F("rate_type", type="select", choices=["Fixed", "Floating"], list=False), F("originated", type="date", list=False),
    F("maturity", type="date"), F("annual_debt_service", "Annual debt service", type="money", list=False),
    F("dscr_covenant", "DSCR covenant", type="float", list=False), F("status", type="select", choices=["Current", "Watch", "Default", "Paid off"]),
], singular="Loan", order_by=Loan.maturity, filters=["kind", "direction"], summary=_loan_summary).register(bp)

Resource("family-office", "shared-expenses", SharedExpense, "Shared Expenses", [
    F("day", "Date", type="date"), F("vendor", required=True), F("description"), F("total", type="money", required=True),
    F("allocation", help="Entity:percent pairs separated by semicolons, e.g. Bhuram Holdings LLC:60; Bhuram Real Estate LP:40"), F("settled", type="bool"),
], singular="Shared expense", order_by=SharedExpense.day.desc(), summary=_shared_summary).register(bp)

Resource("family-office", "transactions", CashTxn, "Transactions", [
    F("day", "Date", type="date", required=True), F("bank_account_id", "Account", type="fk", fk=BankAccount, required=True),
    F("amount", type="money", required=True, help="Negative for outflows"), F("category"), F("counterparty"), F("memo", list=False), F("reconciled", type="bool"),
], singular="Transaction", order_by=CashTxn.day.desc(), filters=["category"], search=["counterparty", "memo", "category"], per_page=60).register(bp)

Resource("family-office", "exchanges", Exchange1031, "1031 Exchanges", [
    F("relinquished", required=True), F("replacement"), F("sale_date", type="date"), F("proceeds", type="money"), F("qi", "Qualified intermediary"),
    F("status", type="select", choices=["Identified", "In contract", "Complete", "Failed"]),
    F("id_deadline", "45-day ID", form=False, fmt=lambda o: D(o.id_deadline)), F("close_deadline", "180-day close", form=False, fmt=lambda o: D(o.close_deadline)),
], singular="Exchange", order_by=Exchange1031.sale_date.desc()).register(bp)

Resource("family-office", "cash", BankAccount, "Cash Accounts", [
    F("name", required=True), F("institution"), ENT(), F("kind", type="select", choices=["Operating", "Money market", "Treasury", "Escrow"]),
    F("last4", "Last 4"), F("balance", type="money"), F("rate", "Rate %", type="float"), F("min_balance", "Minimum", type="money"),
    F("statement_balance", "Statement balance", type="money", list=False),
], singular="Bank account", order_by=BankAccount.balance.desc(), filters=["kind"], summary=_cash_summary).register(bp)

Resource("family-office", "treasury", TreasuryHolding, "Treasury", [
    F("description", required=True), F("cusip", "CUSIP"), F("bank_account_id", "Held at", type="fk", fk=BankAccount), F("face", type="money"),
    F("cost", type="money"), F("yld", "Yield %", type="float"), F("maturity", type="date"),
], singular="Treasury holding", order_by=TreasuryHolding.maturity, summary=_treasury_summary).register(bp)

Resource("family-office", "recurring-cash", RecurringCash, "Recurring Cash", [
    F("name", required=True), ENT(), F("direction", type="select", choices=["in", "out"]), F("amount", type="money", required=True),
    F("frequency", type="select", choices=["Monthly", "Semi-monthly", "Quarterly", "Semi-annual", "Annual"]), F("next_date", type="date"),
    F("category"), F("active", type="bool", default=True),
], singular="Recurring item", order_by=RecurringCash.next_date, filters=["direction"]).register(bp)

Resource("family-office", "family-obligations", FamilyObligation, "Family Obligations", [
    F("person", required=True), F("description"), F("amount", type="money"),
    F("frequency", type="select", choices=["Monthly", "Quarterly", "Semi-annual", "Annual", "One-time"]), F("next_date", type="date"), F("paid_from"),
], singular="Obligation", order_by=FamilyObligation.next_date).register(bp)


def _wire_actions(w):
    if w.status == "Draft":
        return postbtn(url_for("family_office.wire_action", wid=w.id, action="submit"), "Submit")
    if w.status == "Pending approval" and current_user.is_admin and w.requested_by_id != current_user.id:
        return postbtn(url_for("family_office.wire_action", wid=w.id, action="approve"), "Approve", "btn sm green")
    if w.status == "Approved":
        return postbtn(url_for("family_office.wire_action", wid=w.id, action="release"), "Release")
    return ""


Resource("family-office", "wire-forms", Wire, "Wire Forms", [
    F("day", "Date", type="date"), F("bank_account_id", "From account", type="fk", fk=BankAccount), F("beneficiary", required=True),
    F("bank", "Beneficiary bank"), F("amount", type="money", required=True), F("purpose"),
    F("status", type="select", choices=["Draft", "Pending approval", "Approved", "Sent"], form=False, fmt=lambda o: status(o.status)),
    F("approved_by_id", "Approved by", type="fk", fk=User, form=False), F("workflow", "Workflow", form=False, fmt=_wire_actions),
], singular="Wire", order_by=Wire.day.desc(), filters=["status"],
    on_save=lambda o, new: setattr(o, "requested_by_id", current_user.id) if new else None,
    subtitle="Two-person rule: an analyst drafts and submits, a different admin approves, then the wire is released and posted to cash.").register(bp)

Resource("family-office", "bills", Bill, "Bills & Payables", [
    F("payee", required=True), ENT(), F("category"), F("amount", type="money", required=True), F("due", type="date", required=True),
    F("status", type="select", choices=["Open", "Approved", "Paid"]), F("paid_on", type="date", list=False),
], singular="Bill", order_by=Bill.due, filters=["status"], summary=_bills_summary).register(bp)

Resource("family-office", "insurance", InsurancePolicy, "Insurance", [
    F("carrier", required=True), F("kind", "Coverage"), F("insured"), F("coverage", "Limit", type="money"), F("premium", type="money"),
    F("renews", type="date"), F("broker"), F("status", type="select", choices=["Active", "Lapsed", "Quoting"]),
], singular="Policy", order_by=InsurancePolicy.renews).register(bp)

Resource("family-office", "vendors", Vendor, "Vendors", [
    F("name", required=True), F("category"), F("contact"), F("email", type="email"), F("annual_spend", type="money"),
    F("w9_on_file", "W-9 on file", type="bool"), F("status", type="select", choices=["Active", "Inactive"]),
], singular="Vendor", order_by=Vendor.annual_spend.desc(), filters=["category"]).register(bp)

Resource("family-office", "personal-assets", PersonalAsset, "Personal Assets", [
    F("name", required=True), F("kind", type="select", choices=["Residence", "Art", "Vehicle", "Jewelry", "Collectibles", "Aircraft", "Other"]),
    F("location"), F("owner"), F("value", type="money"), F("appraised", type="date"), F("insured", type="bool"),
], singular="Asset", order_by=PersonalAsset.value.desc()).register(bp)

Resource("family-office", "legal-docs", LegalDocument, "Entity Documents", [
    F("title", required=True), F("kind"), ENT(), F("executed", type="date"), F("counsel"), F("location", list=False), F("next_review", type="date"),
], singular="Document", order_by=LegalDocument.next_review).register(bp)

Resource("family-office", "contracts", Contract, "Contracts", [
    F("title", required=True), F("counterparty"),
    F("kind", type="select", choices=["Lease", "Services", "Engagement", "Side letter", "Subscription", "NDA", "Other"]),
    ENT(), F("start", type="date", list=False), F("end", type="date"), F("value", type="money"), F("auto_renew", type="bool"),
    F("status", type="select", choices=["Active", "Expired", "Terminated"]),
], singular="Contract", order_by=Contract.end, filters=["kind"]).register(bp)

Resource("family-office", "matters", LegalMatter, "Legal Matters", [
    F("title", required=True), F("kind"), F("counsel"), F("opened", type="date"), F("exposure", type="money"), F("budget", type="money"),
    F("spent", type="money"), F("status", type="select", choices=["Open", "Closed"]), F("next_step"),
], singular="Matter", order_by=LegalMatter.opened.desc(), filters=["status"]).register(bp)

Resource("family-office", "tax-filings", TaxFiling, "Tax Filings", [
    ENT(), F("form", required=True), F("year", type="int", required=True), F("due", type="date"), F("extended_to", type="date"),
    F("preparer"), F("status", type="select", choices=["Not started", "In progress", "Extended", "Filed"]),
], singular="Filing", order_by=[TaxFiling.year.desc(), TaxFiling.due], filters=["status", "year"]).register(bp)

Resource("family-office", "k1s", K1, "K-1 Tracker", [
    F("investment_id", "Investment", type="fk", fk=Investment, required=True), F("year", type="int"), F("expected", type="date"),
    F("received", type="date"), F("estimate", "Estimate only", type="bool"),
    F("state", "Status", form=False, fmt=lambda o: status("Received") if o.received else (status("Late") if o.expected and o.expected < date.today() else status("Pending"))),
], singular="K-1", order_by=K1.expected, summary=_k1_summary).register(bp)

Resource("family-office", "estimated-tax", EstimatedTax, "Estimated Taxes", [
    ENT(), F("jurisdiction"), F("quarter"), F("due", type="date"), F("amount", type="money"), F("paid_on", type="date"),
], singular="Payment", order_by=EstimatedTax.due).register(bp)

Resource("family-office", "compliance", ComplianceItem, "Compliance Calendar", [
    ENT(), F("item", required=True), F("authority"), F("due", type="date"), F("status", type="select", choices=["Pending", "Filed", "Overdue"]),
], singular="Item", order_by=ComplianceItem.due, filters=["status"]).register(bp)

Resource("family-office", "entity-records", Entity, "Entities", [
    F("name", required=True), F("kind", type="select", choices=["Trust", "LLC", "LP", "Foundation", "Individual", "S-Corp"]),
    F("parent_id", "Parent", type="fk", fk=Entity), F("ownership_pct", "Owned %", type="float"), F("jurisdiction"), F("ein_hint", "EIN (masked)", list=False),
    F("formed", type="date", list=False), F("manager", list=False), F("purpose", list=False),
], singular="Entity", order_by=Entity.id, nav="family_office.entities").register(bp)

Resource("family-office", "property-records", Property, "Property records", [
    F("name", required=True), ENT(), F("kind", type="select", choices=["Multifamily", "Industrial", "Retail", "Office", "Self-storage", "Hospitality", "Land"]),
    F("address", list=False), F("city"), F("state"), F("metro", list=False), F("units", type="int"), F("sqft", "Sq ft", type="int", list=False),
    F("purchase_price", type="money", list=False), F("acquired", type="date", list=False), F("fmv", "FMV", type="money"),
    F("ownership_pct", "Owned %", type="float", list=False), F("noi_t12", "NOI (T-12)", type="money"), F("revenue_t12", "Revenue (T-12)", type="money", list=False),
    F("opex_t12", "Opex (T-12)", type="money", list=False), F("occupancy", "Occupancy %", type="float"), F("capex_budget", type="money", list=False),
    F("cap_rate_uw", "UW cap rate %", type="float", list=False), F("noi_uw", "UW NOI", type="money", list=False),
    F("status", type="select", choices=["Operating", "Development", "Under contract", "Sold"]), F("manager", list=False),
], singular="Property", order_by=Property.fmv.desc(), nav="family_office.properties").register(bp)


# ======================================================================= pages
@bp.route("/")
def dashboard():
    fos.sync_public_sleeves()
    invs = fos.active_investments()
    alloc = fos.allocation(invs)
    tot_inv = sum(i.invested or 0 for i in invs)
    tot_fmv = sum(i.fmv or 0 for i in invs)
    tot_dist = sum(i.distributions or 0 for i in invs)
    cash = fos.cash_total()
    brokerage = sum(i.fmv or 0 for i in invs if i.asset_class == "Public Equities")
    mort = sum(l.balance or 0 for l in Loan.query.filter_by(kind="Mortgage").all())
    margin = sum(a.margin_debt or 0 for a in BrokerageAccount.query.all())
    props = Property.query.all()
    notes_rec = Loan.query.filter(Loan.direction == "receivable", Loan.kind != "Intercompany").all()
    burn = fos.monthly_burn()
    al = fos.alerts()
    today = date.today()
    bills = Bill.query.filter(Bill.status != "Paid").all()
    due7 = [x for x in bills if today <= x.due <= today + timedelta(days=7)]
    overdue = [x for x in bills if x.due < today]
    maturing = Loan.query.filter(Loan.maturity <= today + timedelta(days=90)).all()
    pending_w = Wire.query.filter_by(status="Pending approval").count()
    months = []
    m = today.replace(day=1)
    for _ in range(6):
        months.append(m)
        m = (m - timedelta(days=1)).replace(day=1)
    months.reverse()
    by_m = defaultdict(float)
    for d in Distribution.query.filter(Distribution.day >= months[0]).all():
        by_m[d.day.replace(day=1)] += d.amount
    ents = defaultdict(lambda: [0.0, 0.0])
    for i in invs:
        if i.entity:
            ents[i.entity.name][0] += i.invested or 0
            ents[i.entity.name][1] += i.fmv or 0
    ent_rows = sorted(ents.items(), key=lambda x: -x[1][1])[:6]
    dot = {"danger": "red", "warn": "", "info": "blue"}
    roi = (tot_fmv + tot_dist - tot_inv) / tot_inv * 100 if tot_inv else 0
    blocks = [
        card("Portfolio value", kpis([("Total FMV (family share)", M(tot_fmv)), ("Invested", M(tot_inv)), ("Distributions", M(tot_dist)), ("Cash", M(cash)),
                                      ("Brokerage", M(brokerage)), ("Margin debt", M(margin)), ("Mortgage debt (gross)", M(mort)),
                                      ("Net (FMV + cash − margin)", M(tot_fmv + cash - margin))], cols=4), right=("Data map →", u("data_map")), flush=False),
        kpis([("Portfolio ROI", P(roi), "(FMV + dist − invested) / invested", "", "#10b981"),
              ("Equity multiple", f"{(tot_fmv + tot_dist) / tot_inv:.2f}x" if tot_inv else "—", "", "", "#6366f1"),
              ("Unrealized G/L", M(tot_fmv - tot_inv + tot_dist, color=True), "", "", "#0ea5e9"),
              ("Active / total", f"{len(invs)} / {Investment.query.count()}", "investments", "", "#8b5cf6"),
              ("Properties", len(props), f"{sum(p.units or 0 for p in props):,} units", "", "#f59e0b"),
              ("Active notes", len(notes_rec), _ms(sum(l.balance or 0 for l in notes_rec)), "", "#ec4899"),
              ("Cash runway", f"{cash / burn:.0f} mo" if burn else "—", f"at {_ms(burn)}/mo burn", "", "#14b8a6")], cols=7),
        card(f"Alerts · {sum(1 for a in al if a[0] == 'danger')} danger · {sum(1 for a in al if a[0] == 'warn')} warn · {sum(1 for a in al if a[0] == 'info')} info",
             [html('<div style="max-height:200px;overflow:auto">'), lst([(t, s, None, dot[k]) for k, t, s in al], empty="No alerts."), html("</div>")], flush=True),
        kpis([("Bills due (7d)", len(due7), _ms(sum(x.amount for x in due7)), "neg" if due7 else "", "#ef4444"),
              ("Overdue bills", len(overdue), _ms(sum(x.amount for x in overdue)), "neg" if overdue else "", "#ef4444"),
              ("Maturing (90d)", len(maturing), "loans expiring", "neg" if maturing else "", "#f59e0b"),
              ("Pending approvals", pending_w, "wires awaiting approval", "warn" if pending_w else "", "#8b5cf6")]),
        row(card("Asset allocation", [chart(donut(list(alloc.keys()), [round(v["fmv"]) for v in alloc.values()]), 220),
                                      table(["Type", ">#", ">Invested", ">%"], [[k, v["n"], M(v["invested"]), f"{v['fmv'] / (tot_fmv or 1) * 100:.1f}%"] for k, v in alloc.items()])],
                 right=("Details →", u("allocation")), flush=False),
            card("Distribution trend (6mo)", [chart(bar_chart([x.strftime("%b %Y") for x in months], [round(by_m[x]) for x in months], "Distributions", color="#059669"), 220),
                                               table(["Month", ">Amount"], [[x.strftime("%B %Y"), M(by_m[x])] for x in months])], right=("Details →", u("distributions_list")), flush=False),
            card("Entity breakdown", [chart(bar_chart([e[:24] for e, _ in ent_rows], [round(v[1]) for _, v in ent_rows], "FMV", horizontal=True,
                                                      colors=["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#0ea5e9"]), 220),
                                      table(["Entity", ">Invested", ">FMV", ">G/L"], [[e, M(v[0]), M(v[1]), M(v[1] - v[0], color=True)] for e, v in ent_rows])],
                 right=("Details →", u("entities")), flush=False)),
    ]
    return render("Executive Dashboard", blocks, sub=f"As of {today:%B %d, %Y} · public-equity sleeves synced live from Stocks")


def _org_html():
    ents = Entity.query.all()
    kids = defaultdict(list)
    for e in ents:
        kids[e.parent_id].append(e)
    inv_by = defaultdict(float)
    for i in Investment.query.filter_by(status="Active").all():
        inv_by[i.entity_id] += i.fmv or 0
    cash_by = defaultdict(float)
    for a in BankAccount.query.all():
        cash_by[a.entity_id] += a.balance or 0

    def node(e, depth):
        s = (f'<div style="margin-left:{depth * 26}px;padding:7px 10px;border-left:2px solid #c7d2fe;margin-top:6px;background:#fafbff;border-radius:0 8px 8px 0">'
             f'<a href="{url_for("family_office.entity_records_edit", obj_id=e.id)}"><b>{escape(e.name)}</b></a> <span class="pill gray">{escape(e.kind or "")}</span> '
             f'<span class="small muted">{escape(e.jurisdiction or "")} · {e.ownership_pct or 100:.0f}% · investments ${inv_by[e.id]:,.0f} · cash ${cash_by[e.id]:,.0f}</span></div>')
        return s + "".join(node(c, depth + 1) for c in kids[e.id])
    return "".join(node(e, 0) for e in kids[None])


@bp.route("/data-map/")
def data_map():
    counts = [("Entities", Entity.query.count(), u("entities")), ("Investments", Investment.query.count(), u("investments_list")),
              ("Properties", Property.query.count(), u("properties")), ("Loans", Loan.query.count(), u("loans_list")),
              ("Bank accounts", BankAccount.query.count(), u("cash_list")), ("Cash transactions", CashTxn.query.count(), u("transactions_list")),
              ("Distributions", Distribution.query.count(), u("distributions_list")), ("Valuations", Valuation.query.count(), u("valuations_list")),
              ("Bills", Bill.query.count(), u("bills_list")), ("Brokerage accounts", BrokerageAccount.query.count(), u("brokerage"))]
    flows = [("Stocks", "Brokerage positions and cash", "Public-equity sleeves, Brokerage page, net worth"),
             ("Real Estate", "Properties, loans, monthly P&Ls", "RE pages, allocation, DSCR alerts"),
             ("PE / VC", "Private positions, calls, marks", "Investments, valuation, expected cash"),
             ("Documents", "Filed statements and notices", "Distribution tie-out, K-1 tracker"),
             ("Philanthropy", "Grants paid from the Foundation", "Cash, recurring cash"),
             ("Tasks", "Close checklist and sign-offs", "Close page"),
             ("IR Portal", "Co-investor capital accounts", "Capital account report")]
    return render("Data Map", [
        note("Every app reads and writes the same PostgreSQL database. This map shows which records feed which pages."),
        kpis([(n, c, link("open →", l)) for n, c, l in counts[:5]], cols=5), kpis([(n, c, link("open →", l)) for n, c, l in counts[5:]], cols=5),
        card("Flows into the Family Office ledger", table(["Source app", "Records", "Feeds"], [[b(a), r, f] for a, r, f in flows], sortable=False)),
        card("Entity tree", html(_org_html()), flush=False),
    ], sub="Where each number comes from")


@bp.route("/pfs/")
def pfs():
    fos.sync_public_sleeves()
    nw = fos.net_worth()
    alloc = fos.allocation()
    assets = [(k, v["fmv"]) for k, v in alloc.items() if k != "Real Estate"] + [("Real estate equity", nw["re_equity"]), ("Cash & equivalents", nw["cash"]),
                                                                                ("Notes receivable", nw["receivables"]), ("Personal assets", nw["personal"])]
    liabs = [(l.name, l.balance) for l in Loan.query.filter_by(direction="payable").filter(Loan.property_id.is_(None)).all()] + [("Accounts payable", nw["payables"])]
    return render("Personal Financial Statement", [
        kpis([("Total assets", M(nw["assets"]), "", "", "#10b981"), ("Total liabilities", M(nw["liabilities"] + nw["payables"]), "excl. property-level debt", "neg", "#ef4444"),
              ("Net worth", M(nw["net"]), "family share", "", "#6366f1")]),
        row(card("Assets", table(["Line", ">Amount", ">%"], [[a, M(v), f"{v / (nw['assets'] or 1) * 100:.1f}%"] for a, v in assets], foot=["Total", M(nw["assets"]), "100%"], sortable=False)),
            card("Liabilities", table(["Line", ">Amount"], [[a, M(v)] for a, v in liabs], foot=["Total", M(nw["liabilities"] + nw["payables"])], sortable=False))),
        card("Asset mix", chart(donut([a for a, _ in assets], [round(v) for _, v in assets]), 280)),
    ], sub=f"Statement date {date.today():%B %d, %Y}", actions=[("Net worth report", u("report_net_worth"))])


@bp.route("/investments/map/")
def investment_map():
    import json
    invs = Investment.query.filter(Investment.lat.isnot(None), Investment.status == "Active").all()
    pts = [dict(n=i.name, c=i.asset_class, v=i.fmv or 0, lat=i.lat, lon=i.lon, url=url_for("family_office.investments_edit", obj_id=i.id)) for i in invs]
    h = ('<div id="map" style="height:560px;border-radius:10px"></div>'
         '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
         "<script>document.addEventListener('DOMContentLoaded',function(){var pts=" + json.dumps(pts).replace("<", "\\u003c") + ";var m=L.map('map').setView([37.5,-92],4);"
         "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; OpenStreetMap'}).addTo(m);"
         "var esc=function(s){var d=document.createElement('div');d.textContent=s||'';return d.innerHTML};var col={'Real Estate':'#f59e0b','Private Equity':'#6366f1','Venture Capital':'#10b981'};"
         "pts.forEach(function(p){L.circleMarker([p.lat,p.lon],{radius:Math.max(5,Math.sqrt(p.v)/350),color:col[p.c]||'#64748b',fillOpacity:.55}).addTo(m)"
         ".bindPopup('<b>'+esc(p.n)+'</b><br>'+esc(p.c)+'<br>$'+Math.round(p.v).toLocaleString()+'<br><a href=\"'+p.url+'\">Open</a>');});});</script>")
    return render("Map View", [card(None, html(h), flush=False),
                               card("Locations", table(["Investment", "Class", "City", ">FMV"], [[i.name, i.asset_class, i.city, M(i.fmv)] for i in invs], max_height=320))],
                  sub=f"{len(invs)} located investments", back=("Investments", u("investments_list")))


@bp.route("/entities/")
def entities():
    ents = Entity.query.order_by(Entity.id).all()
    rows = []
    for e in ents:
        invs = Investment.query.filter_by(entity_id=e.id, status="Active").all()
        cash = sum(a.balance or 0 for a in BankAccount.query.filter_by(entity_id=e.id))
        debt = sum(l.balance or 0 for l in Loan.query.filter_by(entity_id=e.id, direction="payable"))
        rows.append([link(e.name, url_for("family_office.entity_records_edit", obj_id=e.id), "tk"), pill(e.kind), e.parent.name if e.parent else "—", e.jurisdiction,
                     len(invs), M(sum(i.invested or 0 for i in invs)), M(sum(i.fmv or 0 for i in invs)), M(cash), M(debt)])
    return render("Entities & Org Chart", [card("Org chart", html(_org_html()), flush=False),
                                           card("Entities", table(["Entity", "Type", "Parent", "Jurisdiction", ">Investments", ">Invested", ">FMV", ">Cash", ">Debt"], rows))],
                  sub=f"{len(ents)} entities", actions=[("+ New entity", url_for("family_office.entity_records_new"), "primary")])


@bp.route("/allocation/")
def allocation():
    fos.sync_public_sleeves()
    invs = fos.active_investments()
    alloc = fos.allocation(invs)
    tot = sum(v["fmv"] for v in alloc.values()) or 1
    targets = {"Public Equities": 40, "Real Estate": 20, "Private Equity": 18, "Venture Capital": 5, "Private Credit": 8, "Hedge Funds": 6, "Alternative Investments": 3}
    classes = list(alloc.keys())
    rows = [[k, v["n"], M(v["invested"]), M(v["fmv"]), f"{v['fmv'] / tot * 100:.1f}%", f"{targets.get(k, 0)}%", P(v["fmv"] / tot * 100 - targets.get(k, 0), 1)] for k, v in alloc.items()]
    by_ent = defaultdict(lambda: defaultdict(float))
    for i in invs:
        by_ent[i.entity.name if i.entity else "—"][i.asset_class] += i.fmv or 0
    cmp = dict(type="bar", pct=True, data=dict(labels=classes, datasets=[dict(label="Actual %", data=[round(alloc[c]["fmv"] / tot * 100, 1) for c in classes]),
                                                                          dict(label="Target %", data=[targets.get(c, 0) for c in classes], backgroundColor="#cbd5e1")]))
    return render("Asset Allocation", [
        row(card("Current mix", chart(donut(classes, [round(alloc[c]["fmv"]) for c in classes]), 300)), card("Actual vs target", chart(cmp, 300))),
        card("By asset class", table(["Asset class", ">#", ">Invested", ">FMV", ">Actual", ">Target", ">Drift"], rows)),
        card("By entity and class", table(["Entity"] + [">" + c for c in classes], [[e] + [M(v.get(c, 0)) for c in classes] for e, v in by_ent.items()])),
    ], sub=f"Total {_ms(tot)} across {len(invs)} active investments")


def _irr(i):
    yrs = max(0.5, date.today().year - (i.vintage or date.today().year) + 0.5)
    m = i.moic
    return ((m ** (1 / yrs)) - 1) * 100 if m and m > 0 else None


@bp.route("/performance/")
def performance():
    invs = [i for i in fos.active_investments() if i.invested]
    by_class = defaultdict(lambda: [0.0, 0.0])
    for i in invs:
        by_class[i.asset_class][0] += i.invested or 0
        by_class[i.asset_class][1] += i.total_value
    rows = sorted(invs, key=lambda i: -(i.moic or 0))
    return render("Performance", [
        card("Multiple by asset class", chart(bar_chart(list(by_class), [round(v[1] / v[0], 2) if v[0] else 0 for v in by_class.values()], "MOIC", money=False), 240)),
        card("By investment", table(["Investment", "Class", ">Vintage", ">Invested", ">FMV", ">Distributions", ">Total value", ">MOIC", ">Approx. IRR", ">Target IRR"],
                                    [[link(i.name, url_for("family_office.investments_edit", obj_id=i.id)), i.asset_class, i.vintage, M(i.invested), M(i.fmv), M(i.distributions),
                                      M(i.total_value), f"{i.moic:.2f}x" if i.moic else "—", P(_irr(i)), f"{i.target_irr:.0f}%" if i.target_irr else "—"] for i in rows])),
    ], sub="MOIC = (FMV + distributions) / invested; IRR approximated from MOIC and holding period")


@bp.route("/pnl/")
def pnl():
    year = date.today().year
    rows = defaultdict(lambda: defaultdict(float))
    for t in CashTxn.query.filter(CashTxn.day >= date(year, 1, 1)).all():
        ent = t.bank_account.entity.name if t.bank_account.entity else "—"
        rows[ent]["Income" if t.amount > 0 else "Expense"] += t.amount
        rows[ent][t.category] += t.amount
    for d in Distribution.query.filter(Distribution.day >= date(year, 1, 1)).all():
        if d.investment.entity:
            rows[d.investment.entity.name]["Distributions"] += d.amount
    out = [[b(e), M(v["Income"]), M(v["Expense"]), M(v["Distributions"]), M(v["Income"] + v["Expense"], color=True)] for e, v in sorted(rows.items())]
    cats = defaultdict(float)
    for v in rows.values():
        for k, x in v.items():
            if k not in ("Income", "Expense", "Distributions") and x < 0:
                cats[k] += -x
    return render("P&L by Entity", [card(f"{year} year to date", table(["Entity", ">Cash in", ">Cash out", ">Distributions recorded", ">Net cash"], out)),
                                    card("Expenses by category", bars(sorted(cats.items(), key=lambda x: -x[1]), "#ef4444"), flush=False)],
                  sub="From bank transactions and recorded distributions")


@bp.route("/portfolio-analytics/")
def analytics():
    invs = fos.active_investments()
    tot = sum(i.fmv or 0 for i in invs) or 1
    top = sorted(invs, key=lambda i: -(i.fmv or 0))[:10]
    by_sector = defaultdict(float)
    by_sponsor = defaultdict(float)
    by_vintage = defaultdict(float)
    for i in invs:
        by_sector[i.sector or "Other"] += i.fmv or 0
        by_sponsor[i.sponsor or "Direct"] += i.fmv or 0
        if i.vintage:
            by_vintage[i.vintage] += i.invested or 0
    hhi = sum(((i.fmv or 0) / tot * 100) ** 2 for i in invs)
    unf = sum(i.unfunded or 0 for i in invs)
    vint = sorted(by_vintage)
    return render("Portfolio Analytics", [
        kpis([("Top-10 concentration", f"{sum(i.fmv or 0 for i in top) / tot * 100:.1f}%", "of FMV", "", "#6366f1"),
              ("HHI", f"{hhi:,.0f}", "concentration index (0–10,000)", "warn" if hhi > 1500 else "", "#f59e0b"),
              ("Unfunded commitments", MS(unf), "future capital calls", "", "#ef4444"), ("Sectors", len(by_sector), "", "", "#10b981")]),
        row(card("Exposure by sector", bars(sorted(by_sector.items(), key=lambda x: -x[1])[:12], "#6366f1"), flush=False),
            card("Exposure by sponsor", bars(sorted(by_sponsor.items(), key=lambda x: -x[1])[:12], "#0ea5e9"), flush=False)),
        row(card("Capital by vintage", chart(bar_chart([str(v) for v in vint], [round(by_vintage[v]) for v in vint], "Invested", color="#8b5cf6"), 240)),
            card("Top 10 positions", table(["Investment", ">FMV", ">% of total"], [[i.name, M(i.fmv), f"{(i.fmv or 0) / tot * 100:.1f}%"] for i in top], sortable=False))),
    ], sub="Concentration, exposure and pacing")


@bp.route("/deal-parameters/")
def deal_parameters():
    invs = [i for i in fos.active_investments() if i.target_irr or i.target_moic]
    return render("Deal Parameters", [
        note("Underwriting terms captured at commitment. Edit any row to update targets, fees and waterfall terms."),
        card("Terms by investment", table(["Investment", "Type", "Sponsor", ">Target IRR", ">Target MOIC", ">Hold (yrs)", ">Pref", ">Promote", ">Mgmt fee", ">Actual MOIC"],
                                          [[link(i.name, url_for("family_office.investments_edit", obj_id=i.id)), i.deal_type, i.sponsor,
                                            f"{i.target_irr:.1f}%" if i.target_irr else "—", f"{i.target_moic:.2f}x" if i.target_moic else "—",
                                            i.hold_years or "—", f"{i.pref_return:.0f}%" if i.pref_return else "—", f"{i.promote:.0f}%" if i.promote else "—",
                                            f"{i.mgmt_fee:.2f}%" if i.mgmt_fee else "—", f"{i.moic:.2f}x" if i.moic else "—"] for i in invs])),
    ], sub=f"{len(invs)} investments with underwriting targets")


@bp.route("/sold-deals/")
def sold_deals():
    sold = Investment.query.filter_by(status="Sold").order_by(Investment.sold_on.desc()).all()
    inv = sum(i.invested or 0 for i in sold)
    proceeds = sum(i.distributions or 0 for i in sold)
    return render("Sold Deals", [
        kpis([("Realized deals", len(sold), "", "", "#6366f1"), ("Capital invested", MS(inv), "", "", "#0ea5e9"), ("Total proceeds", MS(proceeds), "", "pos", "#10b981"),
              ("Realized multiple", f"{proceeds / inv:.2f}x" if inv else "—", "", "", "#f59e0b")]),
        card("Exits", table(["Investment", "Class", ">Vintage", "Sold", ">Invested", ">Proceeds", ">Gain", ">MOIC"],
                            [[link(i.name, url_for("family_office.investments_edit", obj_id=i.id)), i.asset_class, i.vintage, D(i.sold_on), M(i.invested), M(i.distributions),
                              M((i.distributions or 0) - (i.invested or 0), color=True), f"{i.moic:.2f}x" if i.moic else "—"] for i in sold])),
    ])


@bp.route("/non-marketable/")
def non_marketable():
    invs = [i for i in fos.active_investments() if not i.marketable]
    tot = sum(i.fmv or 0 for i in invs)
    return render("Non-Marketable", [
        kpis([("Illiquid positions", len(invs), "", "", "#6366f1"), ("Illiquid FMV", MS(tot), f"{tot / (sum(x.fmv or 0 for x in fos.active_investments()) or 1) * 100:.0f}% of portfolio", "", "#f59e0b"),
              ("Unfunded", MS(sum(i.unfunded or 0 for i in invs)), "", "", "#ef4444")]),
        card("Positions", table(["Investment", "Class", "Sponsor", ">Commitment", ">Called", ">Unfunded", ">FMV", "Last mark"],
                                [[link(i.name, url_for("family_office.investments_edit", obj_id=i.id)), i.asset_class, i.sponsor, M(i.commitment), M(i.invested),
                                  M(i.unfunded), M(i.fmv), D(i.last_mark)] for i in sorted(invs, key=lambda x: -(x.fmv or 0))])),
    ])


@bp.route("/collections/")
def collections():
    assets = PersonalAsset.query.filter(PersonalAsset.kind.in_(["Art", "Collectibles", "Jewelry", "Vehicle", "Aircraft"])).order_by(PersonalAsset.value.desc()).all()
    by = defaultdict(float)
    for a in assets:
        by[a.kind] += a.value or 0
    stale = [a for a in assets if not a.appraised or (date.today() - a.appraised).days > 3 * 365]
    return render("Collections", [
        kpis([("Items", len(assets), "", "", "#6366f1"), ("Appraised value", MS(sum(by.values())), "", "", "#10b981"),
              ("Appraisal older than 3 years", len(stale), "", "warn" if stale else "", "#f59e0b"), ("Uninsured", len([a for a in assets if not a.insured]), "", "neg", "#ef4444")]),
        row(card("By category", chart(donut(list(by), [round(v) for v in by.values()]), 240)),
            card("Items", table(["Item", "Category", "Location", ">Value", "Appraised", "Insured"],
                                [[link(a.name, url_for("family_office.personal_assets_edit", obj_id=a.id)), a.kind, a.location, M(a.value), D(a.appraised),
                                  status("Current") if a.insured else status("Missing")] for a in assets], max_height=320))),
    ], actions=[("+ Add item", url_for("family_office.personal_assets_new"), "primary")])


@bp.route("/intercompany/")
def intercompany():
    ic = Loan.query.filter_by(kind="Intercompany").all()
    net = defaultdict(float)
    for l in ic:
        if l.entity:
            net[l.entity.name] += l.balance or 0
        if l.counterparty_entity:
            net[l.counterparty_entity.name] -= l.balance or 0
    return render("Intercompany", [
        note("Each intercompany note has a lender entity and a borrower entity; the balances should net to zero across the family."),
        card("Notes", table(["Note", "Lender", "Borrower", ">Balance", ">Rate", "Maturity"],
                            [[link(l.name, url_for("family_office.loans_edit", obj_id=l.id)), l.entity.name if l.entity else "—",
                              l.counterparty_entity.name if l.counterparty_entity else l.borrower, M(l.balance), f"{l.rate or 0:.2f}%", D(l.maturity)] for l in ic],
                            foot=["Total", "", "", M(sum(l.balance or 0 for l in ic)), "", ""])),
        card("Net position by entity", table(["Entity", ">Net due from / (to) others"], [[e, M(v, color=True)] for e, v in sorted(net.items(), key=lambda x: -x[1])],
                                             foot=["Check (should be 0)", M(sum(net.values()))])),
    ], actions=[("+ New note", url_for("family_office.loans_new"), "primary")])


# ---------------------------------------------------------------- real estate (FO view)
def _plink(p):
    return link(p.name, url_for("family_office.property_detail", pid=p.id), "tk")


@bp.route("/re-dashboard/")
def re_dashboard():
    props = Property.query.filter(Property.status != "Sold").all()
    fmv = sum(p.fmv or 0 for p in props)
    debt = sum(p.debt for p in props)
    noi = sum(p.noi_t12 or 0 for p in props)
    ds = sum(p.debt_service for p in props)
    by_kind = defaultdict(float)
    by_metro = defaultdict(float)
    for p in props:
        by_kind[p.kind] += p.fmv or 0
        by_metro[p.metro or p.city] += p.fmv or 0
    weak = [p for p in props if p.dscr and p.dscr < 1.25]
    return render("RE Dashboard", [
        kpis([("Portfolio FMV", MS(fmv), f"{len(props)} properties", "", "#16a34a"), ("Debt", MS(debt), f"LTV {debt / (fmv or 1) * 100:.0f}%", "", "#ef4444"),
              ("Equity", MS(fmv - debt), "", "pos", "#6366f1"), ("NOI (T-12)", MS(noi), f"cap rate {noi / (fmv or 1) * 100:.2f}%", "", "#0ea5e9"),
              ("Portfolio DSCR", f"{noi / ds:.2f}x" if ds else "—", "", "", "#f59e0b"), ("Units", f"{sum(p.units or 0 for p in props):,}", "", "", "#8b5cf6")]),
        row(card("FMV by property type", chart(donut(list(by_kind), [round(v) for v in by_kind.values()]), 240)),
            card("FMV by metro", bars(sorted(by_metro.items(), key=lambda x: -x[1]), "#16a34a"), flush=False)),
        card("Coverage watch (DSCR < 1.25x)", table(["Property", ">NOI", ">Debt service", ">DSCR"], [[_plink(p), M(p.noi_t12), M(p.debt_service), f"{p.dscr:.2f}x"] for p in weak],
                                                   empty="Every property covers its debt service at 1.25x or better.")),
    ], actions=[("All properties", u("properties"))])


@bp.route("/properties/")
def properties():
    props = Property.query.order_by(Property.fmv.desc()).all()
    return render("Properties", [card(None, table(["Property", "Type", "Location", ">Units", ">FMV", ">Debt", ">Equity", ">LTV", ">NOI T-12", ">DSCR", ">Occupancy", "Status"],
                                                  [[_plink(p), p.kind, f"{p.city}, {p.state}", p.units or "—", M(p.fmv), M(p.debt), M(p.equity), f"{p.ltv:.0f}%",
                                                    M(p.noi_t12), f"{p.dscr:.2f}x" if p.dscr else "—", f"{p.occupancy or 0:.1f}%", status(p.status)] for p in props]))],
                  sub=f"{len(props)} properties", actions=[("+ Add property", url_for("family_office.property_records_new"), "primary")])


@bp.route("/properties/<int:pid>/")
def property_detail(pid):
    p = db.get_or_404(Property, pid)
    ms = sorted(p.months, key=lambda m: m.month)[-24:]
    labels = [m.month.strftime("%b %y") for m in ms]
    return render(p.name, [
        kpis([("FMV", M(p.fmv)), ("Debt", M(p.debt)), ("Equity", M(p.equity)), ("NOI T-12", M(p.noi_t12)), ("DSCR", f"{p.dscr:.2f}x" if p.dscr else "—"),
              ("Occupancy", f"{p.occupancy or 0:.1f}%")]),
        card("Monthly operations", chart(line_chart(labels, {"Revenue": [round(m.revenue or 0) for m in ms], "Opex": [round(m.opex or 0) for m in ms],
                                                             "NOI": [round(m.noi or 0) for m in ms]}), 260)),
        row(card("Facts", table(["Field", "Value"], [["Type", p.kind], ["Address", f"{p.address or ''}, {p.city}, {p.state}"], ["Owner", p.entity.name if p.entity else "—"],
                                                     ["Units / sq ft", f"{p.units or '—'} / {p.sqft or 0:,}"], ["Acquired", D(p.acquired)], ["Purchase price", M(p.purchase_price)],
                                                     ["Manager", p.manager or "—"], ["Underwritten cap rate", f"{p.cap_rate_uw or 0:.2f}%"]], sortable=False)),
            card("Debt", table(["Loan", "Lender", ">Balance", ">Rate", "Maturity"], [[link(l.name, url_for("family_office.loans_edit", obj_id=l.id)), l.lender, M(l.balance),
                                                                                     f"{l.rate or 0:.2f}%", D(l.maturity)] for l in p.loans], empty="Unlevered."))),
        card("Monthly P&L", table(["Month", ">Revenue", ">Opex", ">NOI", ">Occupancy", "Reviewed"],
                                  [[m.month.strftime("%B %Y"), M(m.revenue), M(m.opex), M(m.noi), f"{m.occupancy or 0:.1f}%", status("Done") if m.reviewed else status("Pending")]
                                   for m in reversed(ms)], max_height=360)),
    ], back=("Properties", u("properties")), active="family_office.properties",
        actions=[("Edit", url_for("family_office.property_records_edit", obj_id=p.id), "")])


@bp.route("/re-financials/")
def re_financials():
    props = Property.query.filter(Property.status != "Sold").all()
    start = (date.today().replace(day=1) - timedelta(days=365)).replace(day=1)
    by_m = defaultdict(lambda: [0.0, 0.0, 0.0])
    for m in PropertyMonth.query.filter(PropertyMonth.month >= start).all():
        r = by_m[m.month]
        r[0] += m.revenue or 0
        r[1] += m.opex or 0
        r[2] += m.noi or 0
    ks = sorted(by_m)
    return render("RE Financials", [
        card("Portfolio NOI, trailing 12 months", chart(line_chart([k.strftime("%b %y") for k in ks], {"Revenue": [round(by_m[k][0]) for k in ks],
                                                                                                      "Opex": [round(by_m[k][1]) for k in ks], "NOI": [round(by_m[k][2]) for k in ks]}), 260)),
        card("By property (T-12)", table(["Property", ">Revenue", ">Opex", ">NOI", ">Margin", ">Occupancy"],
                                         [[_plink(p), M(p.revenue_t12), M(p.opex_t12), M(p.noi_t12), f"{(p.noi_t12 or 0) / (p.revenue_t12 or 1) * 100:.0f}%",
                                           f"{p.occupancy or 0:.1f}%"] for p in props])),
    ], actions=[("Review queue", u("re_review"))])


@bp.route("/report-card/")
def report_card():
    props = Property.query.filter(Property.status != "Sold").all()
    rows = []
    for p in props:
        noi_var = ((p.noi_t12 or 0) - (p.noi_uw or 0)) / (p.noi_uw or 1) * 100 if p.noi_uw else None
        score = 0
        score += 1 if (p.dscr or 0) >= 1.35 else 0
        score += 1 if (p.occupancy or 0) >= 92 else 0
        score += 1 if noi_var is not None and noi_var >= 0 else 0
        score += 1 if p.ltv <= 60 else 0
        grade = "ABCDF"[4 - score] if score < 5 else "A"
        rows.append([_plink(p), pill(grade, {"A": "green", "B": "green", "C": "amber", "D": "red", "F": "red"}[grade]), f"{p.dscr:.2f}x" if p.dscr else "—",
                     f"{p.occupancy or 0:.1f}%", P(noi_var), f"{p.ltv:.0f}%"])
    return render("Report Card", [note("Grade = one point each for DSCR ≥ 1.35x, occupancy ≥ 92%, NOI at or above underwriting, LTV ≤ 60%."),
                                  card(None, table(["Property", "Grade", ">DSCR", ">Occupancy", ">NOI vs UW", ">LTV"], rows))])


@bp.route("/underwriting/")
def underwriting():
    props = Property.query.filter(Property.noi_uw.isnot(None)).all()
    return render("Underwriting vs Actual", [card(None, table(["Property", ">UW NOI", ">Actual NOI", ">Variance", ">UW cap rate", ">Actual cap rate"],
                                                              [[_plink(p), M(p.noi_uw), M(p.noi_t12), M((p.noi_t12 or 0) - (p.noi_uw or 0), color=True),
                                                                f"{p.cap_rate_uw or 0:.2f}%", f"{p.cap_rate:.2f}%"] for p in props]))])


@bp.route("/re-financials/review/")
def re_review():
    pending = PropertyMonth.query.filter_by(reviewed=False).order_by(PropertyMonth.month.desc()).limit(80).all()
    rows = []
    for m in pending:
        flag = []
        if m.noi is not None and m.revenue and m.noi / m.revenue < 0.3:
            flag.append("Low margin")
        if (m.occupancy or 100) < 88:
            flag.append("Occupancy < 88%")
        rows.append([_plink(m.property), m.month.strftime("%B %Y"), M(m.revenue), M(m.opex), M(m.noi), ", ".join(flag) or "—",
                     postbtn(url_for("family_office.re_review_mark", mid=m.id), "Mark reviewed")])
    return render("Financials Review", [card(f"{len(pending)} months awaiting review", table(["Property", "Month", ">Revenue", ">Opex", ">NOI", "Flags", ""], rows,
                                                                                          empty="All monthly statements are reviewed."))],
                  back=("RE Financials", u("re_financials")))


@bp.route("/re-financials/review/<int:mid>", methods=["POST"])
@write_required
def re_review_mark(mid):
    m = db.get_or_404(PropertyMonth, mid)
    m.reviewed = True
    audit("family-office", "review", "property_month", m.id, f"{m.property.name} {m.month:%Y-%m}")
    db.session.commit()
    flash(f"{m.property.name} {m.month:%B %Y} marked reviewed.", "success")
    return redirect(u("re_review"))


@bp.route("/debt/")
def debt():
    loans = Loan.query.filter_by(direction="payable").order_by(Loan.maturity).all()
    by_year = defaultdict(float)
    for l in loans:
        if l.maturity:
            by_year[l.maturity.year] += l.balance or 0
    ys = sorted(by_year)
    tot = sum(l.balance or 0 for l in loans)
    fl = sum(l.balance or 0 for l in loans if l.rate_type == "Floating")
    return render("Debt", [
        kpis([("Total debt", MS(tot), f"{len(loans)} loans", "", "#ef4444"), ("Floating", f"{fl / (tot or 1) * 100:.0f}%", MS(fl), "warn", "#f59e0b"),
              ("Annual debt service", MS(sum(l.annual_debt_service or 0 for l in loans)), "", "", "#6366f1")]),
        card("Maturity ladder", chart(bar_chart([str(y) for y in ys], [round(by_year[y]) for y in ys], "Maturing balance", color="#ef4444"), 220)),
        card("Loans", table(["Loan", "Kind", "Lender", "Property", ">Balance", ">Rate", "Type", "Maturity", ">DSCR", "Status"],
                            [[link(l.name, url_for("family_office.loans_edit", obj_id=l.id)), l.kind, l.lender, _plink(l.property) if l.property else "—", M(l.balance),
                              f"{l.rate or 0:.2f}%", l.rate_type, D(l.maturity), f"{l.property.dscr:.2f}x" if l.property and l.property.dscr else "—", status(l.status)] for l in loans])),
    ], actions=[("+ New loan", url_for("family_office.loans_new"), "primary")])


# ---------------------------------------------------------------- cash
def _freq_dates(start, freq, until):
    step = {"Monthly": 30, "Semi-monthly": 15, "Quarterly": 91, "Semi-annual": 182, "Annual": 365}.get(freq)
    d = start
    while d and d <= until:
        yield d
        if not step:
            break
        d = d + timedelta(days=step)


def _forecast(weeks=13):
    today = date.today()
    end = today + timedelta(weeks=weeks)
    ev = []
    for r in RecurringCash.query.filter_by(active=True).all():
        for d in _freq_dates(r.next_date, r.frequency, end):
            if d >= today:
                ev.append((d, r.name, r.amount if r.direction == "in" else -r.amount, "Recurring"))
    for x in Bill.query.filter(Bill.status != "Paid").all():
        ev.append((max(x.due, today), x.payee, -x.amount, "Bill"))
    for c in CapitalCall.query.filter_by(status="Pending").all():
        if c.due <= end:
            ev.append((max(c.due, today), f"Capital call · {c.investment.name}", -c.amount, "Capital call"))
    for t in TreasuryHolding.query.all():
        if t.maturity and today <= t.maturity <= end:
            ev.append((t.maturity, f"T-bill maturity · {t.description}", t.face, "Treasury"))
    for o in FamilyObligation.query.all():
        for d in _freq_dates(o.next_date, o.frequency, end):
            if d >= today:
                ev.append((d, f"{o.person} · {o.description}", -(o.amount or 0), "Family"))
    return sorted(ev)


@bp.route("/cash-hub/")
def cash_hub():
    cash = fos.cash_total()
    tre = fos.treasury_total()
    ev = _forecast(4)
    out30 = sum(-a for d, _, a, _k in ev if a < 0)
    in30 = sum(a for d, _, a, _k in ev if a > 0)
    recent = CashTxn.query.order_by(CashTxn.day.desc()).limit(10).all()
    links = [("Cash accounts", "cash_list"), ("Cash report", "cash_report"), ("Treasury", "treasury_list"), ("Forecast", "cash_forecast"),
             ("Expected cash", "expected_cash"), ("Cash grid", "cash_grid"), ("Recurring", "recurring_cash_list"), ("Wires", "wire_forms_list"),
             ("Bills", "bills_list"), ("Brokerage", "brokerage"), ("Recon", "cashflow_recon"), ("Close", "close")]
    return render("Cash Hub", [
        kpis([("Cash", MS(cash), "bank and money market", "", "#10b981"), ("Treasury bills", MS(tre), "at cost", "", "#6366f1"),
              ("Next 4 weeks out", MS(out30), f"{len([e for e in ev if e[2] < 0])} payments", "neg", "#ef4444"), ("Next 4 weeks in", MS(in30), "", "pos", "#0ea5e9"),
              ("Monthly burn", MS(fos.monthly_burn()), "recurring outflows", "", "#f59e0b")]),
        html('<div class="grid g6" style="gap:10px">' + "".join(f'<a class="card" style="padding:14px;font-weight:600" href="{u(ep)}">{t} →</a>' for t, ep in links) + "</div>"),
        row(card("Upcoming (4 weeks)", table(["Date", "Item", "Type", ">Amount"], [[D(d), n, k, M(a, color=True)] for d, n, a, k in ev[:25]], max_height=360)),
            card("Recent transactions", table(["Date", "Account", "Counterparty", ">Amount"], [[D(t.day), t.bank_account.name, t.counterparty, M(t.amount, color=True)] for t in recent]),
                 right=("All →", u("transactions_list")))),
    ])


@bp.route("/cash-report/")
def cash_report():
    accts = BankAccount.query.order_by(BankAccount.entity_id).all()
    since = date.today() - timedelta(days=30)
    flows = defaultdict(lambda: [0.0, 0.0])
    for t in CashTxn.query.filter(CashTxn.day >= since).all():
        flows[t.bank_account_id][0 if t.amount > 0 else 1] += t.amount
    rows = [[a.name, a.entity.name if a.entity else "—", a.institution, a.kind, M(a.balance - flows[a.id][0] - flows[a.id][1]), M(flows[a.id][0]),
             M(flows[a.id][1]), M(a.balance), f"{a.rate or 0:.2f}%"] for a in accts]
    return render("Cash Report", [card("Last 30 days by account", table(["Account", "Entity", "Bank", "Kind", ">Opening", ">Inflows", ">Outflows", ">Closing", ">Rate"], rows,
                                                                         foot=["Total", "", "", "", "", M(sum(f[0] for f in flows.values())), M(sum(f[1] for f in flows.values())),
                                                                               M(sum(a.balance or 0 for a in accts)), ""]))],
                  sub=f"{since:%b %d} – {date.today():%b %d, %Y}")


@bp.route("/cash-forecast/")
def cash_forecast():
    weeks = int(request.args.get("weeks", 13))
    ev = _forecast(weeks)
    start = fos.cash_total()
    today = date.today()
    labels, bal, ins, outs = [], [], [], []
    run = start
    for w in range(weeks):
        a, z = today + timedelta(weeks=w), today + timedelta(weeks=w + 1)
        wi = sum(x[2] for x in ev if a <= x[0] < z and x[2] > 0)
        wo = sum(x[2] for x in ev if a <= x[0] < z and x[2] < 0)
        run += wi + wo
        labels.append(a.strftime("%b %d"))
        ins.append(round(wi))
        outs.append(round(wo))
        bal.append(round(run))
    cfg = dict(type="bar", money=True, data=dict(labels=labels, datasets=[dict(label="Inflows", data=ins, backgroundColor="#10b981"),
                                                                          dict(label="Outflows", data=outs, backgroundColor="#ef4444"),
                                                                          dict(label="Ending cash", data=bal, type="line", borderColor="#6366f1", yAxisID="y")]))
    return render("Cash Forecast", [
        kpis([("Starting cash", M(start)), (f"Ending cash ({weeks} wks)", M(run)), ("Lowest week", M(min(bal) if bal else start)), ("Events", len(ev))]),
        card(f"{weeks}-week forecast", chart(cfg, 300), right=None),
        card("Events", table(["Date", "Item", "Type", ">Amount"], [[D(d), n, k, M(a, color=True)] for d, n, a, k in ev], max_height=420)),
    ], sub="Recurring items, open bills, pending capital calls, T-bill maturities and family obligations",
        actions=[("4 weeks", u("cash_forecast", weeks=4)), ("13 weeks", u("cash_forecast", weeks=13)), ("26 weeks", u("cash_forecast", weeks=26))])


@bp.route("/expected-cash/")
def expected_cash():
    calls = CapitalCall.query.order_by(CapitalCall.due).all()
    pend = [c for c in calls if c.status == "Pending"]
    accts = BankAccount.query.filter_by(kind="Operating").all()
    rows = [[link(c.investment.name, url_for("family_office.investments_edit", obj_id=c.investment_id)), D(c.notice_date), D(c.due), M(c.amount), status(c.status),
             postbtn(url_for("family_office.pay_call", cid=c.id), "Fund call", "btn sm green") if c.status == "Pending" else ""] for c in calls]
    exp_d = []
    for i in fos.active_investments():
        if i.distributions and i.vintage and i.asset_class in ("Private Equity", "Real Estate", "Private Credit"):
            exp_d.append((i.name, (i.distributions or 0) / max(1, date.today().year - i.vintage) / 4))
    return render("Expected Cash", [
        kpis([("Pending calls", len(pend), MS(sum(c.amount for c in pend)), "neg" if pend else "", "#ef4444"),
              ("Expected quarterly distributions", MS(sum(v for _, v in exp_d)), "run-rate estimate", "pos", "#10b981"),
              ("Operating cash", MS(sum(a.balance or 0 for a in accts)), "available to fund", "", "#6366f1")]),
        card("Capital calls", table(["Investment", "Notice", "Due", ">Amount", "Status", ""], rows)),
        card("Expected distributions (quarterly run-rate)", bars(sorted(exp_d, key=lambda x: -x[1])[:12], "#10b981"), flush=False),
    ])


@bp.route("/calls/<int:cid>/pay", methods=["POST"])
@write_required
def pay_call(cid):
    c = db.get_or_404(CapitalCall, cid)
    if c.status != "Pending":
        abort(400)
    acct = BankAccount.query.filter_by(entity_id=c.investment.entity_id, kind="Operating").first() or BankAccount.query.filter_by(kind="Operating").order_by(BankAccount.balance.desc()).first()
    c.status = "Funded"
    c.investment.invested = (c.investment.invested or 0) + c.amount
    acct.balance = (acct.balance or 0) - c.amount
    db.session.add(CashTxn(bank_account_id=acct.id, day=date.today(), amount=-c.amount, category="Capital call", counterparty=c.investment.sponsor or c.investment.name,
                           memo=f"Capital call · {c.investment.name}"))
    audit("family-office", "fund", "capital_call", c.id, f"{c.investment.name} ${c.amount:,.0f} from {acct.name}")
    db.session.commit()
    flash(f"Funded ${c.amount:,.0f} to {c.investment.name} from {acct.name}.", "success")
    return redirect(u("expected_cash"))


@bp.route("/cash-grid/")
def cash_grid():
    months = []
    m = date.today().replace(day=1)
    for _ in range(12):
        months.append(m)
        m = (m - timedelta(days=1)).replace(day=1)
    months.reverse()
    grid = defaultdict(lambda: defaultdict(float))
    for t in CashTxn.query.filter(CashTxn.day >= months[0]).all():
        grid[t.category or "Other"][t.day.replace(day=1)] += t.amount
    cats = sorted(grid, key=lambda c: sum(grid[c].values()))
    rows = [[c] + [M(grid[c][x], color=True) if grid[c][x] else "" for x in months] + [M(sum(grid[c].values()), color=True)] for c in cats]
    foot = ["Net"] + [M(sum(grid[c][x] for c in cats), color=True) for x in months] + [M(sum(sum(v.values()) for v in grid.values()), color=True)]
    return render("Cash Grid", [card("Net cash by category and month", table(["Category"] + [">" + x.strftime("%b %y") for x in months] + [">Total"], rows, foot=foot))],
                  sub="Trailing 12 months, all bank accounts")


@bp.route("/brokerage/")
def brokerage():
    accts = BrokerageAccount.query.all()
    by = defaultdict(float)
    for p in pf.positions(by_account=True):
        for a in p.accounts:
            by[a.id] += p.mv
    rows = [[link(a.name, url_for("stocks.holdings")), a.code, a.custodian, a.kind, M(by[a.id]), M(a.cash), M(a.margin_debt), M(by[a.id] + (a.cash or 0) - (a.margin_debt or 0))]
            for a in accts]
    tot = sum(by.values())
    return render("Brokerage", [
        note("Read live from the Stocks app — the same database tables, no import step."),
        kpis([("Securities", MS(tot)), ("Cash", MS(sum(a.cash or 0 for a in accts))), ("Margin debt", MS(sum(a.margin_debt or 0 for a in accts))),
              ("Net", MS(tot + sum((a.cash or 0) - (a.margin_debt or 0) for a in accts)))]),
        card("Accounts", table(["Account", "Code", "Custodian", "Type", ">Securities", ">Cash", ">Margin", ">Net"], rows)),
    ], actions=[("Open Stocks →", url_for("stocks.dashboard"))])


@bp.route("/cashflow-recon/")
def cashflow_recon():
    dists = Distribution.query.order_by(Distribution.day.desc()).limit(150).all()
    txns = CashTxn.query.filter(CashTxn.category == "Distribution").all()
    rows = []
    matched = 0
    for d in dists:
        hit = next((t for t in txns if abs(t.amount - d.amount) < 1 and abs((t.day - d.day).days) <= 5), None)
        matched += 1 if hit else 0
        rows.append([D(d.day), d.investment.name, M(d.amount), (f"{t.bank_account.name} · {D(t.day)}" if (t := hit) else "—"),
                     status("Reconciled") if hit or d.tied_out else status("Unreconciled")])
    return render("Cash Flow Reconciliation", [
        kpis([("Distributions checked", len(dists)), ("Matched to bank", matched, "", "pos"), ("Unmatched", len(dists) - matched, "", "warn")]),
        card("Distributions vs bank deposits (±$1, ±5 days)", table(["Date", "Investment", ">Amount", "Bank match", "Status"], rows, max_height=520)),
    ])


# ---------------------------------------------------------------- wires
@bp.route("/wire-forms/<int:wid>/<action>", methods=["POST"])
@write_required
def wire_action(wid, action):
    w = db.get_or_404(Wire, wid)
    if action == "submit" and w.status == "Draft":
        w.status = "Pending approval"
        w.requested_by_id = w.requested_by_id or current_user.id
    elif action == "approve" and w.status == "Pending approval":
        if not current_user.is_admin:
            abort(403)
        if w.requested_by_id == current_user.id:
            flash("Two-person rule: a different admin must approve this wire.", "error")
            return redirect(u("wire_forms_list"))
        w.status = "Approved"
        w.approved_by_id = current_user.id
    elif action == "release" and w.status == "Approved":
        acct = w.bank_account or BankAccount.query.filter_by(kind="Operating").first()
        acct.balance = (acct.balance or 0) - w.amount
        db.session.add(CashTxn(bank_account_id=acct.id, day=date.today(), amount=-w.amount, category="Wire", counterparty=w.beneficiary, memo=w.purpose))
        w.status = "Sent"
    else:
        abort(400)
    audit("family-office", action, "wire", w.id, f"{w.beneficiary} ${w.amount:,.0f} → {w.status}")
    db.session.commit()
    flash(f"Wire to {w.beneficiary}: {w.status}.", "success")
    return redirect(u("wire_forms_list"))


# ---------------------------------------------------------------- close
def _periods():
    return [p for (p,) in db.session.query(CloseTask.period).distinct().order_by(CloseTask.period.desc()).all()]


@bp.route("/close/")
def close():
    periods = _periods()
    period = request.args.get("period") or (periods[0] if periods else date.today().strftime("%Y-%m"))
    tasks = CloseTask.query.filter_by(period=period).filter(CloseTask.bank_account_id.is_(None)).order_by(CloseTask.due, CloseTask.id).all()
    done = len([t for t in tasks if t.status == "Done"])
    by_area = defaultdict(list)
    for t in tasks:
        by_area[t.area].append(t)
    blocks = [kpis([("Period", period), ("Tasks", len(tasks)), ("Done", done, f"{done / (len(tasks) or 1) * 100:.0f}%", "pos"),
                    ("Open", len(tasks) - done, "", "warn" if len(tasks) - done else "")])]
    for area, ts in by_area.items():
        blocks.append(card(area, table(["Task", "Owner", "Due", "Status", ""],
                                       [[t.task, t.owner, D(t.due), status(t.status),
                                         postbtn(url_for("family_office.close_toggle", tid=t.id), "Reopen" if t.status == "Done" else "Mark done")] for t in ts], sortable=False)))
    nxt = (datetime.strptime(periods[0] + "-01", "%Y-%m-%d").date() + timedelta(days=32)).strftime("%Y-%m") if periods else period
    return render("Monthly Close", blocks, sub="Checklist for the books of every entity",
                  actions=[(p, u("close", period=p), "primary" if p == period else "") for p in periods[:4]]
                  + [("Bank recs", u("close_recon", period=period)), ("post", f"Start {nxt}", u("close_new_period"), "dark", f"Create the {nxt} checklist?")])


@bp.route("/close/task/<int:tid>", methods=["POST"])
@write_required
def close_toggle(tid):
    t = db.get_or_404(CloseTask, tid)
    t.status = "Not started" if t.status == "Done" else "Done"
    audit("family-office", "close", "close_task", t.id, f"{t.period} {t.task} → {t.status}")
    db.session.commit()
    return redirect(request.referrer or u("close", period=t.period))


@bp.route("/close/new", methods=["POST"])
@write_required
def close_new_period():
    periods = _periods()
    if not periods:
        abort(400)
    last = periods[0]
    nxt_d = datetime.strptime(last + "-01", "%Y-%m-%d").date() + timedelta(days=32)
    nxt = nxt_d.strftime("%Y-%m")
    if CloseTask.query.filter_by(period=nxt).first():
        flash(f"{nxt} already exists.", "error")
        return redirect(u("close", period=nxt))
    for t in CloseTask.query.filter_by(period=last).all():
        due = t.due + timedelta(days=(nxt_d.replace(day=1) - datetime.strptime(last + "-01", "%Y-%m-%d").date()).days) if t.due else None
        db.session.add(CloseTask(period=nxt, area=t.area, task=t.task, owner=t.owner, due=due, status="Not started", bank_account_id=t.bank_account_id,
                                 book_balance=t.bank_account.balance if t.bank_account else None))
    audit("family-office", "create", "close_period", None, nxt)
    db.session.commit()
    flash(f"Created the {nxt} close checklist.", "success")
    return redirect(u("close", period=nxt))


@bp.route("/close/recon/", methods=["GET", "POST"])
def close_recon():
    periods = _periods()
    period = request.values.get("period") or (periods[0] if periods else "")
    if request.method == "POST":
        if not current_user.can_write:
            abort(403)
        t = db.get_or_404(CloseTask, int(request.form["tid"]))
        t.statement_balance = float(request.form.get("statement_balance") or 0)
        t.status = "Done" if abs((t.book_balance or 0) - t.statement_balance) < 0.01 else "In progress"
        audit("family-office", "reconcile", "close_task", t.id, f"{t.bank_account.name if t.bank_account else ''} stmt {t.statement_balance:,.2f}")
        db.session.commit()
        flash("Statement balance saved.", "success")
        return redirect(u("close_recon", period=period))
    recs = CloseTask.query.filter_by(period=period).filter(CloseTask.bank_account_id.isnot(None)).all()
    tok = _csrf()
    rows = []
    for t in recs:
        diff = (t.statement_balance or 0) - (t.book_balance or 0) if t.statement_balance is not None else None
        frm = (f'<form method="post" style="display:flex;gap:6px"><input type="hidden" name="csrf_token" value="{tok}"><input type="hidden" name="tid" value="{t.id}">'
               f'<input type="hidden" name="period" value="{period}"><input class="inp" name="statement_balance" type="number" step="0.01" value="{t.statement_balance or ""}" style="width:140px">'
               f'<button class="btn sm">Save</button></form>')
        rows.append([t.bank_account.name, M(t.book_balance, 2), html(frm)["html"], M(diff, 2, color=True) if diff is not None else "—", status(t.status)])
    return render("Bank Reconciliations", [card(f"Period {period}", table(["Account", ">Book balance", "Statement balance", ">Difference", "Status"], rows, sortable=False))],
                  back=("Monthly Close", u("close", period=period)), active="family_office.close_recon")


# ---------------------------------------------------------------- reports
REPORTS = [("net-worth", "Net Worth Statement", "report_net_worth"), ("capital-accounts", "Capital Accounts", "report_capital_accounts"),
           ("quarterly", "Quarterly Investment Report", "report_quarterly")]


@bp.route("/reports/", methods=["GET", "POST"])
def reports():
    if request.method == "POST":
        if not current_user.can_write:
            abort(403)
        key = request.form.get("report")
        name = dict((k, n) for k, n, _ in REPORTS).get(key)
        if not name:
            abort(400)
        nw = fos.net_worth()
        q = (date.today().month - 1) // 3 + 1
        r = ReportRun(report=name, period=f"Q{q} {date.today().year}", generated_by_id=current_user.id, recipients=request.form.get("recipients", ""),
                      summary=f"Net worth ${nw['net']:,.0f}; cash ${nw['cash']:,.0f}; investments ${nw['inv_fmv']:,.0f}", status="Draft")
        db.session.add(r)
        audit("family-office", "generate", "report", None, name)
        db.session.commit()
        flash(f"{name} generated.", "success")
        return redirect(u("reports"))
    runs = ReportRun.query.order_by(ReportRun.created_at.desc()).limit(40).all()
    return render("Reports", [
        html('<div class="grid g3" style="gap:12px">' + "".join(
            f'<div class="card" style="padding:16px"><b>{n}</b><div class="small muted" style="margin:6px 0 12px">Built live from the ledger.</div>'
            f'<a class="btn sm" href="{u(ep)}">View</a> <form method="post" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">'
            f'<input type="hidden" name="report" value="{k}"><button class="btn sm primary">Generate</button></form></div>' for k, n, ep in REPORTS) + "</div>"),
        card("Report history", table(["Report", "Period", "Generated by", "When", "Summary", "Status"],
                                     [[r.report, r.period, r.generated_by.name if r.generated_by else "—", D(r.created_at), r.summary, status(r.status)] for r in runs])),
    ])


@bp.route("/reports/net-worth/")
def report_net_worth():
    fos.sync_public_sleeves()
    nw = fos.net_worth()
    lines = [("Investments (FMV)", nw["inv_fmv"]), ("Real estate equity", nw["re_equity"]), ("Cash", nw["cash"]), ("Notes receivable", nw["receivables"]),
             ("Personal assets", nw["personal"]), ("Liabilities", -nw["liabilities"]), ("Payables", -nw["payables"])]
    return render("Net Worth Statement", [kpis([("Net worth", M(nw["net"])), ("Assets", M(nw["assets"])), ("Liabilities", M(nw["liabilities"] + nw["payables"]))]),
                                          card(None, table(["Line", ">Amount"], [[a, M(v, color=True)] for a, v in lines], foot=["Net worth", M(nw["net"])], sortable=False))],
                  back=("Reports", u("reports")), sub=f"As of {date.today():%B %d, %Y}", actions=[("Print", "javascript:window.print()")])


@bp.route("/reports/capital-accounts/")
def report_capital_accounts():
    rows = []
    for e in Entity.query.order_by(Entity.id).all():
        invs = Investment.query.filter_by(entity_id=e.id).all()
        if not invs:
            continue
        c = sum(i.commitment or 0 for i in invs)
        p = sum(i.invested or 0 for i in invs)
        d = sum(i.distributions or 0 for i in invs)
        f = sum(i.fmv or 0 for i in invs if i.status == "Active")
        rows.append([b(e.name), M(c), M(p), M(c - p), M(d), M(f), f"{(f + d) / p:.2f}x" if p else "—"])
    return render("Capital Accounts", [card(None, table(["Entity", ">Committed", ">Paid-in", ">Unfunded", ">Distributed", ">Ending NAV", ">TVPI"], rows))],
                  back=("Reports", u("reports")), actions=[("Print", "javascript:window.print()")])


@bp.route("/reports/quarterly/")
def report_quarterly():
    today = date.today()
    qs = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    d = Distribution.query.filter(Distribution.day >= qs).all()
    calls = CapitalCall.query.filter(CapitalCall.due >= qs).all()
    vals = Valuation.query.filter(Valuation.day >= qs).all()
    alloc = fos.allocation()
    return render("Quarterly Investment Report", [
        kpis([("Quarter", f"Q{(today.month - 1) // 3 + 1} {today.year}"), ("Distributions", MS(sum(x.amount for x in d))), ("Capital calls", MS(sum(x.amount for x in calls))),
              ("New marks", len(vals))]),
        row(card("Allocation", chart(donut(list(alloc), [round(v["fmv"]) for v in alloc.values()]), 240)),
            card("Distributions this quarter", table(["Date", "Investment", ">Amount"], [[D(x.day), x.investment.name, M(x.amount)] for x in d], max_height=260))),
        card("Valuation changes this quarter", table(["Date", "Investment", "Method", ">FMV"], [[D(v.day), v.investment.name, v.method, M(v.fmv)] for v in vals])),
    ], back=("Reports", u("reports")), actions=[("Print", "javascript:window.print()")])

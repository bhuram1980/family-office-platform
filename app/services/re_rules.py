"""Real-estate issue rules. Each run replaces open auto-generated issues; resolved or snoozed ones stay put."""
from datetime import date, timedelta

from ..extensions import db
from ..models import Loan, Property, REIssue
from . import settings as st

KEYS = [("dscr_min", "Minimum DSCR", "1.25", "number"), ("occupancy_min", "Minimum occupancy %", "90", "number"),
        ("ltv_max", "Maximum LTV %", "65", "number"), ("noi_var_min", "NOI below underwriting by more than %", "10", "number"),
        ("maturity_months", "Flag loan maturities within (months)", "12", "number"),
        ("valuation_basis", "Valuation basis", "Internal mark", ["Internal mark", "Appraisal", "Broker opinion"])]


def thresholds():
    return {k[0]: st.get("real-estate", k[0], k[2], float if k[3] == "number" else str) for k in KEYS}


def run_checks():
    t = thresholds()
    found = []
    today = date.today()
    for p in Property.query.filter(Property.status != "Sold").all():
        if p.dscr and p.dscr < t["dscr_min"]:
            sev = "HIGH" if p.dscr < 1.0 else "MEDIUM"
            found.append((p, sev, "DSCR", f"DSCR {p.dscr:.2f}x below {t['dscr_min']:.2f}x",
                          f"T-12 NOI ${p.noi_t12 or 0:,.0f} covers ${p.debt_service:,.0f} of debt service {p.dscr:.2f} times."))
        if p.occupancy is not None and p.occupancy < t["occupancy_min"]:
            found.append((p, "MEDIUM" if p.occupancy >= t["occupancy_min"] - 5 else "HIGH", "Occupancy", f"Occupancy {p.occupancy:.1f}%",
                          f"Below the {t['occupancy_min']:.0f}% floor."))
        if p.ltv > t["ltv_max"]:
            found.append((p, "MEDIUM", "LTV", f"LTV {p.ltv:.0f}%", f"Debt ${p.debt:,.0f} on value ${p.fmv or 0:,.0f}; limit {t['ltv_max']:.0f}%."))
        if p.noi_uw and p.noi_t12 is not None:
            var = (p.noi_t12 - p.noi_uw) / p.noi_uw * 100
            if var < -t["noi_var_min"]:
                found.append((p, "MEDIUM", "NOI", f"NOI {var:.0f}% vs underwriting", f"T-12 ${p.noi_t12:,.0f} vs underwritten ${p.noi_uw:,.0f}."))
        for l in p.loans:
            if l.maturity and l.maturity <= today + timedelta(days=int(t["maturity_months"] * 30.4)):
                found.append((p, "HIGH" if l.maturity <= today + timedelta(days=180) else "LOW", "Maturity", f"{l.name} matures {l.maturity:%b %Y}",
                              f"${l.balance or 0:,.0f} at {l.rate or 0:.2f}% with {l.lender}."))
    REIssue.query.filter_by(status="Open").delete()
    closed = {(i.property_id, i.title) for i in REIssue.query.filter(REIssue.status != "Open").all()}
    n = 0
    for p, sev, rule, title, detail in found:
        if (p.id, title) in closed:
            continue
        db.session.add(REIssue(property_id=p.id, severity=sev, rule=rule, title=title, detail=detail, status="Open"))
        n += 1
    db.session.flush()
    return n

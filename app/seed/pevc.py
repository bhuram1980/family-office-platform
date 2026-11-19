"""Synthetic PE / VC monitor data: quarterly operating metrics, GP letters, document coverage, reviews."""
from datetime import date, timedelta

from ..extensions import db
from ..models import CompanyMetric, GPUpdate, Investment, PEDocument, PEReview, User

PRIVATE = ["Private Equity", "Venture Capital"]


def quarters(n):
    today = date.today()
    y, q = today.year, (today.month - 1) // 3  # last completed quarter
    if q == 0:
        y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append(f"{y}Q{q}")
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return list(reversed(out))


def q_end(qs):
    y, q = int(qs[:4]), int(qs[-1])
    return date(y, 3 * q, 28) + timedelta(days=4) - timedelta(days=(date(y, 3 * q, 28) + timedelta(days=4)).day)


TEMPLATES = {
    "Positive": ["{co} beat plan on revenue for the quarter", "{co} signed its largest customer to date", "{co} closed an accretive add-on acquisition",
                 "{co} reached cash-flow breakeven"],
    "Neutral": ["Quarterly letter: {co} on plan", "{co} management transition announced", "{co} refinanced its credit facility", "Annual meeting recap — {co}"],
    "Negative": ["{co} missed revenue plan; reforecast issued", "{co} extending runway with cost cuts", "{co} covenant waiver requested from lenders"],
}


def seed(ctx):
    rnd = ctx["rnd"]
    invs = Investment.query.filter(Investment.asset_class.in_(PRIVATE)).all()
    qs = quarters(8)
    users = User.query.filter(User.role.in_(["super_admin", "admin", "analyst"])).all()
    for inv in invs:
        vc = inv.asset_class == "Venture Capital"
        rev = rnd.uniform(4, 30) * 1e6 if vc else rnd.uniform(40, 260) * 1e6
        growth = rnd.uniform(0.04, 0.14) if vc else rnd.uniform(0.005, 0.035)
        margin = rnd.uniform(-0.45, 0.05) if vc else rnd.uniform(0.11, 0.24)
        cash = rnd.uniform(15, 60) * 1e6 if vc else rnd.uniform(10, 50) * 1e6
        hc = int(rev / (220000 if vc else 310000) * 4)
        for q in qs:
            rev *= 1 + growth + rnd.uniform(-0.03, 0.03)
            e = rev * (margin + rnd.uniform(-0.03, 0.03))
            burn = max(0, -e / 3) if vc else 0
            cash = max(1.5e6, cash - burn * 3 + (0 if vc else e * 0.4))
            hc = max(8, int(hc * (1 + growth / 2 + rnd.uniform(-0.02, 0.02))))
            db.session.add(CompanyMetric(investment_id=inv.id, quarter=q, revenue=round(rev, -3), ebitda=round(e, -3), arr=round(rev * 4, -3) if vc else None,
                                         cash=round(cash, -3), burn=round(burn, -3) if vc else None, headcount=hc,
                                         net_debt=None if vc else round(rev * 4 * rnd.uniform(0.6, 1.6), -5)))
        co = inv.name.split(" — ")[0]
        for k in range(rnd.randint(2, 4)):
            mood = rnd.choices(["Positive", "Neutral", "Negative"], [4, 5, 2])[0]
            title = rnd.choice(TEMPLATES[mood]).format(co=co)
            day = date.today() - timedelta(days=rnd.randint(3, 330))
            db.session.add(GPUpdate(investment_id=inv.id, day=day, kind=rnd.choice(["Quarterly letter", "Board update", "Press release", "Capital call notice"]),
                                    title=title, sentiment=mood, read=day < date.today() - timedelta(days=45) or rnd.random() < 0.4,
                                    body=f"{title}. Management reiterated full-year guidance and highlighted pipeline conversion, hiring and working-capital discipline. "
                                         f"Next update expected after quarter end."))
        for q in qs[-4:]:
            for kind in ["Quarterly statement", "Capital account"] + (["Financials"] if not vc else []):
                late = q == qs[-1]
                if rnd.random() < (0.55 if late else 0.93):
                    db.session.add(PEDocument(investment_id=inv.id, period=q, kind=kind, received=q_end(q) + timedelta(days=rnd.randint(25, 75)),
                                              filename=f"{co.replace(' ', '_')}_{q}_{kind.replace(' ', '_')}.pdf"))
        if rnd.random() < 0.55:
            db.session.add(PEReview(investment_id=inv.id, quarter=qs[-1], reviewer_id=rnd.choice(users).id, decision=rnd.choice(["Hold", "Hold", "Hold", "Watch", "Add", "Exit"]),
                                    rating=rnd.randint(2, 5), notes="Reviewed GP statement against operating metrics; mark looks reasonable."))
        if rnd.random() < 0.18:
            inv.attention = rnd.choice(["Mark not updated in two quarters", "Burn above plan", "Covenant waiver requested", "Key-person event at GP"])

"""Two co-investors with profiles, positions, offerings, documents and message threads."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import Deal, Investment, InvestorPosition, InvestorProfile, IRDocument, IRInterest, IRMessage, IROffering, User
from ..services.pdf import make_pdf

PROFILES = {"leah": [("Whitford Family Partners LLC", "LLC"), ("Leah Whitford IRA", "IRA")], "omar": [("Haddad Holdings LLC", "LLC"), ("Omar & Rana Haddad JTWROS", "Joint")]}


def seed(ctx):
    rnd = ctx["rnd"]
    today = date.today()
    pool = Investment.query.filter(Investment.status == "Active", Investment.asset_class.in_(["Real Estate", "Private Equity", "Private Credit"]),
                                   Investment.deal_type.in_(["Direct", "Co-Invest", "Buyout"])).all()
    boss = User.query.filter_by(role="super_admin").first()
    cfo = User.query.filter_by(username="priya").first()
    profs = []
    for un, items in PROFILES.items():
        u_ = User.query.filter_by(username=un).first()
        if not u_:
            continue
        for name, kind in items:
            p = InvestorProfile(user_id=u_.id, name=name, kind=kind, tax_id_last4=f"{rnd.randint(1000, 9999)}", bank_last4=f"{rnd.randint(1000, 9999)}",
                                address=rnd.choice(["410 Glenwood Ave, Raleigh, NC", "88 Harbor Dr, Charleston, SC", "1200 Peachtree St, Atlanta, GA"]))
            db.session.add(p)
            db.session.flush()
            profs.append(p)
            for inv in rnd.sample(pool, min(len(pool), rnd.randint(3, 5))):
                pct = rnd.choice([2.5, 4, 5, 7.5, 10])
                contributed = (inv.invested or 0) * pct / 100
                pos = InvestorPosition(profile_id=p.id, investment_id=inv.id, ownership_pct=pct, commitment=round(contributed * rnd.uniform(1.0, 1.15), -3),
                                       contributed=round(contributed, -2), distributions=round((inv.distributions or 0) * pct / 100, -2),
                                       since=date(inv.vintage or today.year - 2, rnd.randint(1, 12), 1))
                db.session.add(pos)
                q = f"{today.year}Q{max(1, (today.month - 1) // 3)}"
                db.session.add(IRDocument(profile_id=p.id, investment_id=inv.id, title=f"{inv.name} — {q} investor report", kind="Quarterly report", period=q,
                                          content=make_pdf(f"{inv.name} — {q} Investor Report", [f"Prepared for {p.name}", f"Ownership {pct}% of the family position",
                                                                                                 f"Net asset value ${pos.contributed * 1.2:,.0f} (estimate)", "Bhuram Family Office"])))
                db.session.add(IRDocument(profile_id=p.id, investment_id=inv.id, title=f"{inv.name} — {today.year - 1} Schedule K-1", kind="K-1", period=str(today.year - 1),
                                          content=make_pdf("Schedule K-1 (Form 1065)", [f"Partner: {p.name}", f"Investment: {inv.name}", "Tax year " + str(today.year - 1)]),
                                          viewed_at=datetime.utcnow() - timedelta(days=20) if rnd.random() < 0.5 else None))
    deals = Deal.query.filter(Deal.stage.in_(["Diligence", "IC Review", "Approved"])).limit(3).all()
    offs = []
    for d in deals:
        o = IROffering(title=f"{d.name} co-investment", deal_id=d.id, asset_class=d.asset_class, location=d.location, raise_amount=round((d.check_size or 1e6) * 0.5, -5),
                       min_check=250000 if (d.check_size or 0) > 2e6 else 100000, target_irr=d.target_irr, target_close=today + timedelta(days=rnd.randint(20, 60)),
                       summary=f"{d.thesis} The family is investing alongside and is offering a limited allocation to existing co-investors.")
        db.session.add(o)
        offs.append(o)
    db.session.flush()
    if offs and profs:
        db.session.add(IRInterest(offering_id=offs[0].id, profile_id=profs[0].id, amount=250000, status="Indicated"))
    for un in PROFILES:
        u_ = User.query.filter_by(username=un).first()
        if not u_:
            continue
        t0 = datetime.utcnow() - timedelta(days=9)
        db.session.add(IRMessage(investor_id=u_.id, from_id=cfo.id, subject="Q3 reports posted", body=f"Hi {u_.first_name}, your Q3 investor reports are in Documents. "
                                 "Let us know if you have any questions.", at=t0, read_by_investor=True, read_by_office=True))
        db.session.add(IRMessage(investor_id=u_.id, from_id=u_.id, subject="Re: Q3 reports posted", body="Thanks — when should we expect the next distribution?",
                                 at=t0 + timedelta(days=2), read_by_investor=True, read_by_office=False))
        db.session.add(IRMessage(investor_id=u_.id, from_id=boss.id, subject="New co-investment opportunity", body="We've opened a limited allocation in a new deal. "
                                 "Details are under Deals in the portal.", at=t0 + timedelta(days=5), read_by_investor=False, read_by_office=True))

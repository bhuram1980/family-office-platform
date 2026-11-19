"""29 synthetic deals across the pipeline."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import Deal, DealActivity, DealScore, FollowUp, User
from ..models.deals import CRITERIA

DEALS = [
    ("Harborline Logistics", "Private Equity", "Logistics", "Savannah, GA"), ("Pinecrest Senior Living", "Real Estate", "Senior housing", "Asheville, NC"),
    ("Verdant Soil Sciences", "Venture Capital", "Agtech", "Fresno, CA"), ("Copperleaf Dental Partners", "Private Equity", "Healthcare", "Phoenix, AZ"),
    ("Lumen Grid Storage", "Private Equity", "Energy", "Austin, TX"), ("Northwind Cold Storage", "Real Estate", "Industrial", "Columbus, OH"),
    ("Quillfeather Software", "Venture Capital", "Software", "Denver, CO"), ("Bramble Pet Health", "Private Equity", "Consumer", "Minneapolis, MN"),
    ("Saltmarsh Marina Holdings", "Real Estate", "Hospitality", "Charleston, SC"), ("Orion Specialty Lending III", "Private Credit", "Credit", "New York, NY"),
    ("Thistle Robotics", "Venture Capital", "Industrial tech", "Pittsburgh, PA"), ("Gatehouse Self Storage", "Real Estate", "Self-storage", "Boise, ID"),
    ("Meridian Lab Services", "Private Equity", "Healthcare", "Raleigh, NC"), ("Ashgrove Flex Industrial", "Real Estate", "Industrial", "Reno, NV"),
    ("Tallgrass Water Rights", "Alternative Investments", "Water", "Bozeman, MT"), ("Kiteline Payments", "Venture Capital", "Fintech", "Chicago, IL"),
    ("Redstone HVAC Roll-up", "Private Equity", "Services", "Dallas, TX"), ("Ember Hill Apartments", "Real Estate", "Multifamily", "Nashville, TN"),
    ("Clearpath Behavioral", "Private Equity", "Healthcare", "Tampa, FL"), ("Fable Learning", "Venture Capital", "Edtech", "Seattle, WA"),
    ("Granite Bay Senior Debt II", "Private Credit", "Credit", "San Francisco, CA"), ("Wrenfield Medical Office", "Real Estate", "Office", "Charlotte, NC"),
    ("Silverline Aviation Parts", "Private Equity", "Aerospace", "Wichita, KS"), ("Mossbrook Timberland", "Alternative Investments", "Timber", "Eugene, OR"),
    ("Halfmoon Coffee Co.", "Private Equity", "Consumer", "Portland, OR"), ("Beacon Point Industrial", "Real Estate", "Industrial", "Indianapolis, IN"),
    ("Cinder Labs", "Venture Capital", "Biotech", "Cambridge, MA"), ("Riverstone Car Wash Portfolio", "Real Estate", "Retail", "San Antonio, TX"),
    ("Juniper Home Health", "Private Equity", "Healthcare", "Salt Lake City, UT"),
]
SPONSORS = ["Tidewater Capital", "Sable Ridge Partners", "Granite Peak Advisors", "Westbrook Equity", "Lantern Hill Capital", "Direct / founder", "Cobalt Bay Partners"]
SOURCES = ["GP relationship", "Banker", "Co-investor referral", "Inbound", "Family network", "Conference"]


def seed(ctx):
    rnd = ctx["rnd"]
    people = User.query.filter(User.role.in_(["super_admin", "admin", "analyst"])).all()
    today = date.today()
    stage_w = [("Inbox", 5), ("Screening", 7), ("Diligence", 5), ("IC Review", 3), ("Approved", 2), ("Closed", 3), ("Passed", 4)]
    stages = [s for s, n in stage_w for _ in range(n)]
    rnd.shuffle(stages)
    for (name, cls, sector, loc), stg in zip(DEALS, stages):
        vc = cls == "Venture Capital"
        size = rnd.choice([8, 12, 20, 35, 60, 90, 150, 250]) * 1e6
        d = Deal(name=name, sponsor=rnd.choice(SPONSORS), asset_class=cls, sector=sector, location=loc, stage=stg, size=size,
                 check_size=round(size * rnd.uniform(0.02, 0.12), -5), target_irr=round(rnd.uniform(22, 35) if vc else rnd.uniform(12, 24), 1),
                 target_moic=round(rnd.uniform(3, 6) if vc else rnd.uniform(1.6, 2.8), 1), hold_years=rnd.choice([3, 4, 5, 6, 7]), source=rnd.choice(SOURCES),
                 owner_id=rnd.choice(people).id, received=today - timedelta(days=rnd.randint(3, 200)),
                 next_step=rnd.choice(["Schedule management call", "Request data room access", "Review QoE draft", "Draft IC memo", "Reference calls", "Negotiate side letter"]),
                 thesis=f"{name} is a {sector.lower()} opportunity in {loc} with a credible plan to grow earnings and a sponsor we know.",
                 risks=rnd.choice(["Customer concentration", "Execution risk on expansion", "Leverage at entry", "Key-person dependency", "Regulatory change"]))
        if stg == "Passed":
            d.pass_reason = rnd.choice(["Valuation too rich", "Outside mandate", "Weak downside case", "Sponsor alignment"])
            d.decision_date = d.received + timedelta(days=rnd.randint(10, 60))
        if stg in ("Approved", "Closed"):
            d.decision_date = d.received + timedelta(days=rnd.randint(30, 90))
        db.session.add(d)
        db.session.flush()
        if stg != "Inbox":
            for c in CRITERIA:
                base = 4 if stg in ("Approved", "Closed", "IC Review") else (2 if stg == "Passed" else 3)
                db.session.add(DealScore(deal_id=d.id, criterion=c, score=max(1, min(5, base + rnd.choice([-1, 0, 0, 1])))))
        for _ in range(rnd.randint(0, 2)):
            db.session.add(FollowUp(deal_id=d.id, owner_id=rnd.choice(people).id, due=today + timedelta(days=rnd.randint(-6, 20)),
                                    note=rnd.choice(["Send NDA back", "Ask for monthly KPIs", "Call the CFO", "Get lender term sheet", "Check references", "Circulate IC memo"]),
                                    done=rnd.random() < 0.25))
        db.session.add(DealActivity(deal_id=d.id, user_id=d.owner_id, at=datetime.combine(d.received, datetime.min.time()), text=f"Deal received from {d.source.lower()}."))
        if stg not in ("Inbox",):
            db.session.add(DealActivity(deal_id=d.id, user_id=d.owner_id, at=datetime.combine(d.received + timedelta(days=5), datetime.min.time()), text=f"Moved to {stg}."))

"""Synthetic giving history for the Alladin Foundation."""
from datetime import date, timedelta

from ..extensions import db
from ..models import DAFTxn, GivingBudget, Grant, Recipient, Tuition, User
from ..models.philanthropy import CAUSES

ORGS = [("Riverside Literacy Project", "Education"), ("Triangle Food Network", "Human services"), ("Blue Ridge Land Conservancy", "Environment"),
        ("Carolina Children's Hospital Foundation", "Health"), ("Oak City Youth Orchestra", "Arts & culture"), ("Hope Street Shelter", "Human services"),
        ("Coastal Marine Research Institute", "Research"), ("Durham Community Health Clinic", "Health"), ("Sri Venkateswara Temple Fund", "Faith"),
        ("Neuse River Keepers", "Environment"), ("First Generation Scholars", "Education"), ("Pine Hollow Animal Rescue", "Community"),
        ("Raleigh Museum of Art", "Arts & culture"), ("Habitat Builders of Wake County", "Community"), ("Alzheimer's Research Alliance", "Research"),
        ("Women in STEM Mentors", "Education"), ("Veterans Bridge Home", "Human services"), ("Tar Heel Literacy Council", "Education")]
SCHOOLS = [("Ravenscroft Academy", "Education"), ("Duke-area Montessori School", "Education"), ("Wolfpack University", "Education")]


def seed(ctx):
    rnd = ctx["rnd"]
    staff = User.query.filter(User.role.in_(["super_admin", "admin", "analyst"])).all()
    admins = User.query.filter(User.role.in_(["super_admin", "admin"])).all()
    today = date.today()
    recs = []
    for n, c in ORGS:
        r = Recipient(name=n, kind="Charity", cause=c, ein=f"{rnd.randint(10, 99)}-{rnd.randint(1000000, 9999999)}", city=rnd.choice(["Raleigh, NC", "Durham, NC", "Chapel Hill, NC", "Wilmington, NC", "Asheville, NC"]),
                      contact=rnd.choice(["Executive Director", "Development Office", "Board Chair"]), email=f"giving@{n.split()[0].lower()}-example.org", verified=rnd.random() > 0.08)
        db.session.add(r)
        recs.append(r)
    schools = []
    for n, c in SCHOOLS:
        r = Recipient(name=n, kind="School", cause=c, city="Raleigh, NC", contact="Bursar", email=f"bursar@{n.split()[0].lower()}-example.edu", verified=True)
        db.session.add(r)
        schools.append(r)
    db.session.flush()
    for y in (today.year - 1, today.year):
        for c in CAUSES:
            db.session.add(GivingBudget(year=y, cause=c, amount=rnd.choice([40, 60, 80, 100, 150, 200]) * 1000))
    bal = 1_850_000.0
    db.session.add(DAFTxn(day=date(today.year - 1, 1, 2), kind="Contribution", amount=bal, memo="Opening balance"))
    for m in range(23):
        d = (date(today.year - 1, 1, 1) + timedelta(days=31 * m)).replace(day=15)
        if d > today:
            break
        if m % 3 == 0:
            db.session.add(DAFTxn(day=d, kind="Contribution", amount=125_000, memo="Quarterly funding from Foundation operating"))
        db.session.add(DAFTxn(day=d.replace(day=28), kind="Investment gain", amount=round(rnd.uniform(-9000, 21000), 2), memo="Pool return"))
        if m % 3 == 2:
            db.session.add(DAFTxn(day=d.replace(day=28), kind="Fee", amount=-round(rnd.uniform(1800, 2600), 2), memo="Sponsor admin fee"))
    for k in range(70):
        r = rnd.choice(recs)
        req = today - timedelta(days=rnd.randint(0, 690))
        amt = rnd.choice([2500, 5000, 10000, 15000, 25000, 50000, 75000, 100000])
        stt = "Paid" if req < today - timedelta(days=40) else rnd.choice(["Requested", "Requested", "Approved", "Paid", "Declined"])
        g = Grant(recipient_id=r.id, amount=amt, requested_on=req, status=stt, source=rnd.choice(["DAF", "DAF", "Foundation"]), cause=r.cause,
                  purpose=rnd.choice(["General operating support", "Annual gala sponsorship", "Capital campaign", "Scholarship fund", "Program support", "Matching gift"]),
                  requested_by_id=rnd.choice(staff).id)
        if stt in ("Approved", "Paid"):
            g.approved_by_id, g.approved_on = rnd.choice(admins).id, req + timedelta(days=rnd.randint(1, 10))
        if stt == "Paid":
            g.paid_on = g.approved_on + timedelta(days=rnd.randint(2, 15))
            g.method = "DAF grant" if g.source == "DAF" else rnd.choice(["Check", "Wire"])
            g.reconciled = g.paid_on < today - timedelta(days=45) or rnd.random() < 0.5
        db.session.add(g)
        db.session.flush()
        if stt == "Paid" and g.source == "DAF" and g.paid_on <= today:
            db.session.add(DAFTxn(day=g.paid_on + timedelta(days=rnd.randint(0, 4)), kind="Grant", amount=-amt, memo=f"Grant to {r.name}", grant_id=g.id if g.reconciled else None))
    kids = ["Anika Alladin", "Rohan Alladin"]
    for y in (today.year - 1, today.year):
        for term, mo in (("Fall", 8), ("Spring", 1)):
            for kid, sch in zip(kids, schools):
                due = date(y, mo, 10)
                db.session.add(Tuition(student=kid, recipient_id=sch.id, term=f"{term} {y}", amount=rnd.choice([18500, 21400, 26750]), due=due,
                                       paid_on=due - timedelta(days=5) if due < today else None))

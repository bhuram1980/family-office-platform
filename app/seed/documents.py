"""Synthetic documents: inbox items with proposals, filed history, emails, e-signatures, requests, hiring and agent runs."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import (AgentRun, Candidate, Deal, DocRequest, Document, InboundEmail, Investment, Property, SignatureRequest, Signer, User)
from ..services.classify import classify
from ..services.pdf import make_pdf


def _doc(rnd, filename, title, lines, source, received, **kw):
    pdf = make_pdf(title, lines)
    text = " ".join([title] + lines)
    c = classify(filename, text)
    d = Document(filename=filename, mime="application/pdf", size=len(pdf), content=pdf, text=text, source=source, received_at=received,
                 proposed_kind=c["kind"], proposed_app=c["app"], confidence=c["confidence"], period=c["period"], amount=c["amount"], **kw)
    if c["target"]:
        setattr(d, f"{c['target'][0]}_id", c["target"][1].id)
    return d


def seed(ctx):
    rnd = ctx["rnd"]
    staff = User.query.filter(User.role.in_(["super_admin", "admin", "analyst"])).all()
    invs = Investment.query.filter(Investment.asset_class.in_(["Private Equity", "Venture Capital", "Private Credit"])).all()
    props = Property.query.all()
    deals = Deal.query.all()
    now = datetime.utcnow()
    q = f"{date.today().year}Q{max(1, (date.today().month - 1) // 3)}"
    templates = [
        ("{n} capital call notice {q}.pdf", "Capital Call Notice", ["Please fund your pro rata share of $ {amt} by the due date.", "Wire instructions on file."], "inv"),
        ("{n} quarterly statement {q}.pdf", "Quarterly Statement", ["Net asset value as of quarter end.", "Ending capital $ {amt}."], "inv"),
        ("{n} distribution notice.pdf", "Distribution Notice", ["A distribution of $ {amt} will be paid on the payment date."], "inv"),
        ("{n} capital account {q}.pdf", "Capital Account Statement", ["Partner capital account rollforward.", "Ending balance $ {amt}."], "inv"),
        ("{n} rent roll and operating statement.pdf", "Property Operating Statement", ["Rent roll, T-12 operating statement and budget variance.", "NOI $ {amt}."], "prop"),
        ("{n} K-1 {y}.pdf", "Schedule K-1 (Form 1065)", ["Partner's share of income, deductions, credits."], "inv"),
        ("{n} teaser and CIM.pdf", "Confidential Information Memorandum", ["Overview of the business, market and financial summary."], "deal"),
        ("Invoice {k} — Hale & Whitlock LLP.pdf", "Invoice", ["Professional services. Amount due $ {amt}."], None),
        ("Operating account bank statement {m}.pdf", "Bank Statement", ["Checking account statement for the period."], None),
    ]
    docs = []
    for i in range(64):
        t = rnd.choice(templates)
        tgt = rnd.choice(invs) if t[3] == "inv" else rnd.choice(props) if t[3] == "prop" else rnd.choice(deals) if t[3] == "deal" else None
        n = tgt.name.split(" — ")[0] if tgt else ""
        amt = f"{rnd.randint(25, 2400) * 1000:,}"
        fn = t[0].format(n=n, q=q, y=date.today().year - 1, k=1000 + i, m=(date.today() - timedelta(days=30 * rnd.randint(1, 6))).strftime("%B %Y")).strip()
        lines = [x.format(amt=amt) for x in t[2]] + [f"Prepared for Alladin Family Office. Reference {rnd.randint(10000, 99999)}."]
        received = now - timedelta(days=rnd.randint(0, 120), hours=rnd.randint(0, 23))
        d = _doc(rnd, fn, t[1], lines, rnd.choice(["Email", "Email", "Dropbox", "Portal", "Upload"]), received)
        if d.source == "Dropbox":
            d.folder = rnd.choice(["/GP Portals/Statements", "/Property Managers/Monthly", "/Scans"])
        inbox = i < 24
        if not inbox:
            d.status = "Filed"
            d.kind = d.proposed_kind
            d.filed_by_id = rnd.choice(staff).id
            d.filed_at = received + timedelta(hours=rnd.randint(1, 72))
        if rnd.random() < 0.1:
            d.flagged, d.flag_reason = True, rnd.choice(["Wire instructions changed vs. prior notice", "Amount differs from ledger", "Duplicate of an earlier upload"])
        if i in (60, 61):
            d.deleted_at = now - timedelta(days=1)
        db.session.add(d)
        docs.append(d)
    db.session.flush()
    for k in range(14):
        d = rnd.choice([x for x in docs if x.source == "Email"])
        e = InboundEmail(from_addr=rnd.choice(["investorrelations@tidewater-example.com", "notices@sableridge-example.com", "am@summit-assets-example.com",
                                               "billing@halewhitlock-example.com", "ops@granitepeak-example.com"]),
                         subject=f"{d.proposed_kind}: {d.filename.rsplit('.', 1)[0]}", body="Please find the attached document. Reply with any questions.",
                         received_at=d.received_at, processed=d.status == "Filed")
        db.session.add(e)
        db.session.flush()
        d.email_id = e.id
    people = [("Priya Raman", "priya@alladin-fo.example"), ("Tirumala", "tirumala@alladin-fo.example"), ("Jordan Ellis (counsel)", "jellis@counsel-example.com"),
              ("Mara Quinn (GP)", "mquinn@gp-example.com")]
    for k, (title, stt) in enumerate([("Subscription agreement — Harborline Logistics co-invest", "Sent"), ("Side letter — Tidewater Fund IV", "Signed"),
                                      ("Engagement letter — 2026 tax compliance", "Signed"), ("Ironwood refinance — loan documents", "Sent"),
                                      ("Grant agreement — Riverside Literacy Project", "Draft"), ("Offer letter — Senior Accountant", "Sent"),
                                      ("Property management agreement — Cedar Bluff", "Declined"), ("Wire authorization — Q4 capital calls", "Signed")]):
        r = SignatureRequest(title=title, status=stt, created_by_id=rnd.choice(staff).id, sent_at=None if stt == "Draft" else now - timedelta(days=rnd.randint(2, 30)),
                             message="Please review and sign.")
        if stt in ("Signed", "Declined"):
            r.completed_at = r.sent_at + timedelta(days=rnd.randint(1, 5))
        db.session.add(r)
        db.session.flush()
        for o, (nm, em) in enumerate(rnd.sample(people, 2), 1):
            s = Signer(request_id=r.id, name=nm, email=em, order=o, status="Signed" if stt == "Signed" else ("Declined" if stt == "Declined" and o == 2 else
                                                                                                            "Signed" if stt in ("Sent", "Declined") and o == 1 else "Pending"))
            if s.status == "Signed":
                s.signed_at = (r.sent_at or now) + timedelta(days=1)
            db.session.add(s)
    for what, frm in [("Q3 quarterly statement", "Tidewater Capital"), ("Updated rent roll", "Summit Asset Services"), ("2025 K-1", "Sable Ridge Partners"),
                      ("Certificate of insurance", "Riverbend Industrial PM"), ("Audited financials FY2025", "Northgate Software"), ("W-9", "Oakline Landscaping"),
                      ("Appraisal report", "Bayview Medical Offices lender"), ("Lender compliance certificate", "Regions Bank"), ("Board deck", "Kestrel Analytics"),
                      ("Signed LPA amendment", "Granite Peak Advisors")]:
        due = date.today() + timedelta(days=rnd.randint(-15, 25))
        stt = rnd.choice(["Requested", "Requested", "Received"])
        db.session.add(DocRequest(what=what, from_party=frm, owner_id=rnd.choice(staff).id, requested_on=due - timedelta(days=21), due=due,
                                  status="Overdue" if stt == "Requested" and due < date.today() else stt))
    for nm, role, stg in [("Avery Lindholm", "Senior Accountant", "Offer"), ("Ruth Okafor", "Investment Analyst", "Interview"), ("Cal Mendes", "Executive Assistant", "Hired"),
                          ("Ines Duval", "Investment Analyst", "Screen"), ("Theo Grant", "Property Accountant", "Declined")]:
        db.session.add(Candidate(name=nm, role=role, stage=stg, resume=True, offer_letter="Signed" if stg == "Hired" else ("Sent" if stg == "Offer" else "—"),
                                 background_check="Clear" if stg == "Hired" else ("In progress" if stg == "Offer" else "—"), i9=stg == "Hired",
                                 start_date=date.today() + timedelta(days=21) if stg in ("Offer", "Hired") else None))
    for k in range(24):
        db.session.add(AgentRun(agent=rnd.choice(["Email intake", "Dropbox sync", "Classifier", "Coverage checker"]), started_at=now - timedelta(hours=6 * k),
                                processed=rnd.randint(0, 9), filed=rnd.randint(0, 5), errors=1 if rnd.random() < 0.08 else 0))

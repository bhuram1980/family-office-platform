from app.extensions import db
from app.models import CashTxn, DAFTxn, Grant, Recipient
from app.blueprints.philanthropy import daf_balance


def test_pages(admin):
    r = Recipient.query.first()
    for url in ["/philanthropy/", "/philanthropy/?tab=grid", "/philanthropy/giving/", "/philanthropy/approvals/", "/philanthropy/directory/", f"/philanthropy/directory/{r.id}/",
                "/philanthropy/reconciliation/", "/philanthropy/grants/", "/philanthropy/documents/", "/philanthropy/settings/", "/philanthropy/grants/new"]:
        assert admin.get(url).status_code == 200, url
    assert daf_balance() > 0


def test_request_approve_pay_daf(login_as):
    r = Recipient.query.first()
    priya = login_as("priya")
    priya.post("/philanthropy/grants/new", {"recipient_id": r.id, "amount": "60000", "source": "DAF", "purpose": "Test gift"})
    g = Grant.query.filter_by(purpose="Test gift").one()
    assert g.status == "Requested" and g.cause == r.cause
    priya.post(f"/philanthropy/grants/{g.id}/approve")
    db.session.refresh(g)
    assert g.status == "Requested"  # same person can't approve a large grant
    boss = login_as("tirumala")
    bal0 = daf_balance()
    boss.post(f"/philanthropy/grants/{g.id}/approve")
    boss.post(f"/philanthropy/grants/{g.id}/pay")
    db.session.refresh(g)
    assert g.status == "Paid" and round(bal0 - daf_balance(), 2) == 60000


def test_foundation_grant_posts_cash(admin):
    r = Recipient.query.first()
    admin.post("/philanthropy/grants/new", {"recipient_id": r.id, "amount": "5000", "source": "Foundation", "purpose": "Cash gift test"})
    g = Grant.query.filter_by(purpose="Cash gift test").one()
    admin.post(f"/philanthropy/grants/{g.id}/approve")
    admin.post(f"/philanthropy/grants/{g.id}/pay")
    assert CashTxn.query.filter_by(counterparty=r.name, amount=-5000).count() == 1


def test_analyst_cannot_approve(login_as):
    g = Grant.query.filter_by(status="Requested").first()
    c = login_as("noah")
    assert c.post(f"/philanthropy/grants/{g.id}/approve").status_code == 403

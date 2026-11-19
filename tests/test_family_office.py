from app.extensions import db
from app.models import BankAccount, CapitalCall, CashTxn, CloseTask, Investment, PropertyMonth, Wire


def test_dashboard_shows_totals(admin):
    r = admin.get("/family-office/")
    assert r.status_code == 200
    assert b"Executive Dashboard" in r.data and b"Asset allocation" in r.data


def test_create_edit_delete_investment(admin):
    r = admin.post("/family-office/investments/new", {"name": "Test Growth Fund IV", "asset_class": "Private Equity", "invested": "1000000",
                                                      "fmv": "1250000", "status": "Active"})
    assert r.status_code == 302
    inv = Investment.query.filter_by(name="Test Growth Fund IV").one()
    assert inv.moic == 1.25
    r = admin.post(f"/family-office/investments/{inv.id}/edit", {"name": "Test Growth Fund IV", "asset_class": "Private Equity", "invested": "1000000",
                                                                 "fmv": "1500000", "status": "Active"})
    assert r.status_code == 302
    db.session.refresh(inv)
    assert inv.fmv == 1500000
    assert admin.post(f"/family-office/investments/{inv.id}/delete").status_code == 302
    assert Investment.query.filter_by(name="Test Growth Fund IV").count() == 0


def test_fund_capital_call_moves_cash(admin):
    c = CapitalCall.query.filter_by(status="Pending").first()
    inv0 = c.investment.invested
    cash0 = sum(a.balance for a in BankAccount.query.all())
    r = admin.post(f"/family-office/calls/{c.id}/pay")
    assert r.status_code == 302
    db.session.refresh(c)
    assert c.status == "Funded"
    assert round(c.investment.invested - inv0, 2) == round(c.amount, 2)
    assert round(cash0 - sum(a.balance for a in BankAccount.query.all()), 2) == round(c.amount, 2)


def test_wire_two_person_rule(login_as):
    analyst = login_as("elena")
    acct = BankAccount.query.filter_by(kind="Operating").first()
    analyst.post("/family-office/wire-forms/new", {"beneficiary": "Test Escrow Co", "amount": "25000", "bank_account_id": acct.id, "purpose": "test"})
    w = Wire.query.filter_by(beneficiary="Test Escrow Co").one()
    assert w.status == "Draft" and w.requested_by.username == "elena"
    analyst.post(f"/family-office/wire-forms/{w.id}/submit")
    assert analyst.post(f"/family-office/wire-forms/{w.id}/approve").status_code == 403
    boss = login_as("tirumala")
    boss.post(f"/family-office/wire-forms/{w.id}/approve")
    db.session.refresh(w)
    assert w.status == "Approved"
    bal0 = acct.balance
    boss.post(f"/family-office/wire-forms/{w.id}/release")
    db.session.refresh(w)
    db.session.refresh(acct)
    assert w.status == "Sent" and round(bal0 - acct.balance, 2) == 25000
    assert CashTxn.query.filter_by(counterparty="Test Escrow Co").count() == 1


def test_viewer_cannot_write(login_as):
    v = login_as("devon")
    assert v.get("/family-office/").status_code in (200, 403)
    c = CapitalCall.query.filter_by(status="Pending").first()
    if c:
        assert v.post(f"/family-office/calls/{c.id}/pay").status_code == 403


def test_close_toggle_and_new_period(admin):
    t = CloseTask.query.filter(CloseTask.bank_account_id.is_(None)).first()
    s0 = t.status
    admin.post(f"/family-office/close/task/{t.id}")
    db.session.refresh(t)
    assert t.status != s0
    periods0 = {p for (p,) in db.session.query(CloseTask.period).distinct()}
    admin.post("/family-office/close/new")
    periods1 = {p for (p,) in db.session.query(CloseTask.period).distinct()}
    assert len(periods1) == len(periods0) + 1


def test_review_month(admin):
    m = PropertyMonth.query.filter_by(reviewed=False).first()
    admin.post(f"/family-office/re-financials/review/{m.id}")
    db.session.refresh(m)
    assert m.reviewed


def test_generate_report(admin):
    r = admin.post("/family-office/reports/", {"report": "net-worth"})
    assert r.status_code == 302
    assert b"Net Worth Statement" in admin.get("/family-office/reports/").data

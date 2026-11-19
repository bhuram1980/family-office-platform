from app.extensions import db
from app.models import BrokerageAccount, Security, StockTxn, TaxLot, TradeProposal, WatchItem
from app.services import portfolio as pf


def test_buy_creates_lot_and_moves_cash(app):
    a = BrokerageAccount.query.filter_by(code="BFN").first()
    s = Security.query.filter_by(ticker="MSFT").first()
    cash0 = a.cash
    lots0 = TaxLot.query.filter_by(account_id=a.id, security_id=s.id).count()
    pf.execute_trade(a, s, "BUY", 10, 100.0)
    db.session.commit()
    assert TaxLot.query.filter_by(account_id=a.id, security_id=s.id).count() == lots0 + 1
    assert round(a.cash, 2) == round(cash0 - 1000, 2)


def test_sell_fifo_realizes_pnl(app):
    a = BrokerageAccount.query.filter_by(code="BFN").first()
    s = Security.query.filter_by(ticker="MSFT").first()
    held = sum(l.shares for l in TaxLot.query.filter_by(account_id=a.id, security_id=s.id))
    txn = pf.execute_trade(a, s, "SELL", 5, 200.0)
    db.session.commit()
    assert txn.realized_pnl is not None
    after = sum(l.shares for l in TaxLot.query.filter_by(account_id=a.id, security_id=s.id))
    assert after == held - 5


def test_cannot_oversell(app):
    import pytest
    a = BrokerageAccount.query.filter_by(code="BFN").first()
    s = Security.query.filter_by(ticker="MSFT").first()
    with pytest.raises(ValueError):
        pf.execute_trade(a, s, "SELL", 10_000_000, 1.0)
    db.session.rollback()


def test_proposal_approve_books_trade(admin):
    p = TradeProposal.query.filter_by(status="pending", action="BUY").first()
    n0 = StockTxn.query.count()
    r = admin.post(f"/stocks/actions/{p.id}/approve")
    assert r.status_code == 302
    db.session.refresh(p)
    assert p.status == "approved"
    assert StockTxn.query.count() == n0 + 1


def test_analyst_cannot_approve(client):
    client.login("marcus")
    p = TradeProposal.query.filter_by(status="pending").first()
    assert client.post(f"/stocks/actions/{p.id}/approve").status_code == 403
    assert client.post(f"/stocks/actions/{p.id}/reject").status_code == 302


def test_crud_watchlist(admin):
    s = Security.query.filter_by(ticker="AAPL").first()
    n0 = WatchItem.query.count()
    r = admin.post("/stocks/watch/new", {"security_id": s.id, "target_price": "150", "note": "test"})
    assert r.status_code == 302
    assert WatchItem.query.count() == n0 + 1
    w = WatchItem.query.order_by(WatchItem.id.desc()).first()
    admin.post(f"/stocks/watch/{w.id}/edit", {"security_id": s.id, "target_price": "155", "note": "edited"})
    db.session.refresh(w)
    assert w.target_price == 155 and w.note == "edited"
    admin.post(f"/stocks/watch/{w.id}/delete")
    assert WatchItem.query.count() == n0


def test_refresh_prices(admin):
    s = Security.query.filter_by(ticker="NVDA").first()
    r = admin.post("/stocks/refresh")
    assert r.status_code == 302


def test_csv_export(admin):
    r = admin.get("/stocks/securities/export.csv")
    assert r.status_code == 200 and b"Ticker" in r.data

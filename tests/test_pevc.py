from app.extensions import db
from app.models import GPUpdate, Investment, PEDocument, PEReview, Valuation
from app.seed.pevc import PRIVATE, quarters


def _pos():
    return Investment.query.filter(Investment.asset_class.in_(PRIVATE), Investment.status == "Active").first()


def test_pages(admin):
    i = _pos()
    for url in ["/pevc/", "/pevc/positions/", f"/pevc/positions/{i.id}/", "/pevc/attention/", "/pevc/operating/", "/pevc/updates/",
                "/pevc/financials/", "/pevc/coverage/", "/pevc/review/"]:
        assert admin.get(url).status_code == 200, url


def test_review_books_mark(admin):
    i = _pos()
    n = Valuation.query.filter_by(investment_id=i.id).count()
    r = admin.post("/pevc/review/", {"investment_id": i.id, "decision": "Watch", "rating": "2", "fmv": "1234567", "notes": "test"})
    assert r.status_code == 302
    db.session.refresh(i)
    assert i.fmv == 1234567
    assert Valuation.query.filter_by(investment_id=i.id).count() == n + 1
    assert PEReview.query.filter_by(investment_id=i.id, quarter=quarters(1)[0]).one().decision == "Watch"


def test_mark_all_read(admin):
    admin.post("/pevc/updates/read-all")
    assert GPUpdate.query.filter_by(read=False).count() == 0


def test_log_documents(admin):
    i = _pos()
    q = quarters(1)[0]
    admin.post(f"/pevc/coverage/{i.id}/{q}")
    kinds = {d.kind for d in PEDocument.query.filter_by(investment_id=i.id, period=q)}
    assert {"Quarterly statement", "Capital account"} <= kinds

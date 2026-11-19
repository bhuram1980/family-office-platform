import io

from app.extensions import db
from app.models import CapitalCall, Document, Investment, PEDocument, SignatureRequest
from app.services.pdf import make_pdf


def test_pages(admin):
    d = Document.query.first()
    for url in ["/documents/", "/documents/dropbox/", "/documents/emails/", "/documents/attachments/", "/documents/coverage/", "/documents/recovery/",
                "/documents/deals/", "/documents/tracker/", "/documents/flags/", "/documents/e-signatures/", "/documents/e-signatures/new", "/documents/hiring/",
                "/documents/audit/", "/documents/agents/", "/documents/settings/", f"/documents/documents/{d.id}/"]:
        assert admin.get(url).status_code == 200, url


def test_upload_classifies_and_filing_posts_capital_call(admin):
    inv = Investment.query.filter_by(asset_class="Private Equity", status="Active").first()
    name = inv.name.split(" — ")[0]
    pdf = make_pdf("Capital Call Notice", [f"{name}", "Please fund $ 123,456 by the due date."])
    r = admin.c.post("/documents/upload", data={"csrf_token": admin.token(), "files": (io.BytesIO(pdf), f"{name} capital call notice.pdf")},
                     content_type="multipart/form-data")
    assert r.status_code == 302
    d = Document.query.filter_by(filename=f"{name} capital call notice.pdf").one()
    assert d.proposed_kind == "Capital call" and d.investment_id == inv.id and d.amount == 123456
    admin.post(f"/documents/documents/{d.id}/approve")
    db.session.refresh(d)
    assert d.status == "Filed"
    assert CapitalCall.query.filter_by(investment_id=inv.id, amount=123456, status="Pending").count() == 1
    dl = admin.get(f"/documents/documents/{d.id}/download")
    assert dl.data.startswith(b"%PDF")


def test_filing_statement_updates_pevc_coverage(admin):
    d = Document.query.filter_by(status="Inbox", proposed_kind="Quarterly statement").filter(Document.investment_id.isnot(None), Document.period.isnot(None)).first()
    PEDocument.query.filter_by(investment_id=d.investment_id, period=d.period, kind="Quarterly statement").delete()
    db.session.commit()
    admin.post(f"/documents/documents/{d.id}/approve")
    assert PEDocument.query.filter_by(investment_id=d.investment_id, period=d.period, kind="Quarterly statement").count() == 1


def test_delete_restore(admin):
    d = Document.query.filter_by(status="Inbox", deleted_at=None).first()
    admin.post(f"/documents/documents/{d.id}/delete")
    db.session.refresh(d)
    assert d.deleted_at
    admin.post(f"/documents/documents/{d.id}/restore")
    db.session.refresh(d)
    assert d.deleted_at is None


def test_esign_order(admin):
    admin.post("/documents/e-signatures/new", {"title": "Test NDA", "name1": "Ann A", "email1": "a@x.example", "name2": "Bob B", "email2": "b@x.example"})
    r = SignatureRequest.query.filter_by(title="Test NDA").one()
    admin.post(f"/documents/e-signatures/{r.id}/send")
    s1, s2 = r.signers
    admin.post(f"/documents/e-signatures/{r.id}/sign", {"sid": s2.id})
    db.session.refresh(s2)
    assert s2.status == "Pending"  # out of order is refused
    admin.post(f"/documents/e-signatures/{r.id}/sign", {"sid": s1.id})
    admin.post(f"/documents/e-signatures/{r.id}/sign", {"sid": s2.id})
    db.session.refresh(r)
    assert r.status == "Signed" and r.completed_at


def test_classifier_agent(admin):
    n0 = Document.query.filter_by(status="Inbox").count()
    admin.post("/documents/agents/classify")
    assert Document.query.filter_by(status="Inbox").count() <= n0

from app.extensions import db
from app.models import InvestorPosition, InvestorProfile, IRDocument, IRInterest, IRMessage, IROffering, User

from .conftest import static_get_routes


def _uid(name):
    return User.query.filter_by(username=name).one().id


def test_pages_staff(admin, app):
    for path in static_get_routes(app, "/ir-portal"):
        assert admin.get(path).status_code == 200, path


def test_pages_investor(login_as):
    c = login_as("leah")
    for path in ["/ir-portal/", "/ir-portal/investments/", "/ir-portal/sites/", "/ir-portal/profiles/", "/ir-portal/deals/",
                 "/ir-portal/documents/", "/ir-portal/messages/", "/ir-portal/profile/"]:
        assert c.get(path).status_code == 200, path
    assert b"Welcome back, Leah" in c.get("/ir-portal/").data


def test_investor_isolation(login_as):
    c = login_as("leah")
    omar = _uid("omar")
    pos = InvestorPosition.query.join(InvestorProfile).filter(InvestorProfile.user_id == omar).first()
    doc = IRDocument.query.join(InvestorProfile).filter(InvestorProfile.user_id == omar).first()
    assert c.get(f"/ir-portal/investments/{pos.id}/").status_code == 404
    assert c.get(f"/ir-portal/documents/{doc.id}/download").status_code == 404
    # "view as" is ignored for investors
    assert b"Welcome back, Leah" in c.get(f"/ir-portal/?as={omar}").data
    prof = InvestorProfile.query.filter_by(user_id=omar).first()
    assert c.post("/ir-portal/profiles/", {"pid": prof.id, "address": "x", "bank_last4": "1111"}).status_code == 404
    # no other apps, no office tools
    for path in ["/family-office/", "/stocks/", "/admin/", "/ir-portal/offerings/", "/ir-portal/office/messages/"]:
        assert c.get(path).status_code in (302, 403, 404), path


def test_indicate_interest_and_message(login_as):
    c = login_as("leah")
    o = IROffering.query.filter_by(status="Open").first()
    prof = InvestorProfile.query.filter_by(user_id=_uid("leah")).first()
    r = c.post(f"/ir-portal/deals/{o.id}/", {"profile_id": prof.id, "amount": (o.min_check or 0) + 50000, "action": "indicate"})
    assert r.status_code == 302
    it = IRInterest.query.filter_by(offering_id=o.id, profile_id=prof.id).one()
    assert it.status == "Indicated"
    assert IRMessage.query.filter_by(read_by_office=False).count() >= 1
    # below minimum is refused
    c.post(f"/ir-portal/deals/{o.id}/", {"profile_id": prof.id, "amount": 1, "action": "commit"})
    db.session.refresh(it)
    assert it.status == "Indicated"
    c.post("/ir-portal/messages/", {"subject": "Hi", "body": "Question about the K-1"})
    assert IRMessage.query.filter_by(body="Question about the K-1").count() == 1


def test_download_marks_viewed(login_as):
    c = login_as("omar")
    doc = IRDocument.query.join(InvestorProfile).filter(InvestorProfile.user_id == _uid("omar"), IRDocument.viewed_at.is_(None)).first()
    r = c.get(f"/ir-portal/documents/{doc.id}/download")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    db.session.refresh(doc)
    assert doc.viewed_at is not None


def test_viewer_cannot_post(login_as):
    c = login_as("devon")
    assert c.post("/ir-portal/messages/", {"body": "x"}).status_code in (403, 302)


def test_investor_does_not_see_staff_announcements(login_as):
    from app.models import Announcement
    a = Announcement.query.filter_by(active=True).first()
    if a:
        assert a.title.encode() not in login_as("leah").get("/ir-portal/").data

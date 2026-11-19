from app.extensions import db
from app.models import Deal, FollowUp, Investment, Setting


def test_pages(admin):
    d = Deal.query.first()
    for url in ["/deals/", "/deals/pipeline/", "/deals/pipeline/?view=table&q=a", f"/deals/deals/{d.id}/", "/deals/compare/?ids=1,2,3",
                "/deals/follow-ups/", "/deals/settings/", "/deals/deals/new"]:
        assert admin.get(url).status_code == 200, url
    assert Deal.query.count() == 29


def test_new_deal_scoring_and_ic_gate(admin):
    admin.post("/deals/deals/new", {"name": "Test Widget Co", "asset_class": "Private Equity", "stage": "Inbox", "check_size": "2000000"})
    d = Deal.query.filter_by(name="Test Widget Co").one()
    admin.post(f"/deals/deals/{d.id}/stage", {"stage": "IC Review"})
    db.session.refresh(d)
    assert d.stage == "Inbox"  # unscored deals can't go to IC
    admin.post(f"/deals/deals/{d.id}/scores", {f"s_{c}": "5" for c in ["Team", "Market", "Terms", "Track record", "Downside protection", "Portfolio fit"]})
    admin.post(f"/deals/deals/{d.id}/stage", {"stage": "IC Review"})
    admin.post(f"/deals/deals/{d.id}/stage", {"stage": "Approved"})
    db.session.refresh(d)
    assert d.stage == "Approved" and d.decision_date
    admin.post(f"/deals/deals/{d.id}/convert")
    db.session.refresh(d)
    assert d.stage == "Closed" and d.investment_id
    assert db.session.get(Investment, d.investment_id).commitment == 2000000


def test_analyst_cannot_approve(login_as):
    d = Deal.query.filter_by(stage="IC Review").first()
    c = login_as("elena")
    # elena has no deals access at all
    assert c.post(f"/deals/deals/{d.id}/stage", {"stage": "Approved"}).status_code == 403
    s = login_as("sofia")
    assert s.post(f"/deals/deals/{d.id}/stage", {"stage": "Approved"}).status_code == 403


def test_followup_flow(admin):
    d = Deal.query.first()
    admin.post(f"/deals/deals/{d.id}/followup", {"note": "Call the auditor", "due": "2030-01-01"})
    f = FollowUp.query.filter_by(note="Call the auditor").one()
    admin.post(f"/deals/followups/{f.id}/done")
    db.session.refresh(f)
    assert f.done


def test_weights_setting(admin):
    data = {k: "1" for k in ["w_team", "w_market", "w_terms", "w_track_record", "w_downside_protection", "w_portfolio_fit"]}
    data.update(w_team="3", min_score_ic="3.2", stale_days="21")
    admin.post("/deals/settings/", data)
    assert Setting.query.filter_by(scope="deals", key="w_team").one().value == "3"

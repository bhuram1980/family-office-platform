from app.extensions import db
from app.models import Property, REIssue, Setting


def test_dashboard(admin):
    r = admin.get("/real-estate/")
    assert r.status_code == 200 and b"Market Watch" in r.data and b"Issue queue" in r.data


def test_resolve_issue_survives_rerun(admin):
    i = REIssue.query.filter_by(status="Open").first()
    admin.post(f"/real-estate/issues/{i.id}/resolve")
    admin.post("/real-estate/run-checks")
    assert REIssue.query.filter_by(property_id=i.property_id, title=i.title, status="Open").count() == 0


def test_threshold_setting_changes_issue_count(admin):
    admin.post("/real-estate/settings/", {"dscr_min": "5", "occupancy_min": "90", "ltv_max": "65", "noi_var_min": "10", "maturity_months": "12",
                                          "valuation_basis": "Internal mark"})
    assert Setting.query.filter_by(scope="real-estate", key="dscr_min").one().value == "5"
    admin.post("/real-estate/run-checks")
    n_dscr = REIssue.query.filter_by(status="Open", rule="DSCR").count()
    assert n_dscr >= len([p for p in Property.query.all() if p.dscr and p.status != "Sold"]) - 2
    admin.post("/real-estate/settings/", {"dscr_min": "1.25", "occupancy_min": "90", "ltv_max": "65", "noi_var_min": "10", "maturity_months": "12",
                                          "valuation_basis": "Internal mark"})


def test_add_month_updates_t12(admin):
    p = Property.query.filter(Property.status != "Sold").first()
    r = admin.post(f"/real-estate/properties/{p.id}/month", {"month": "2031-01", "revenue": "500000", "opex": "200000", "occupancy": "95"})
    assert r.status_code == 302
    db.session.refresh(p)
    assert p.occupancy == 95


def test_qa_answers(admin):
    r = admin.get("/real-estate/ai/?q=Which+properties+have+DSCR+below+1.25%3F")
    assert b"below 1.25x DSCR" in r.data

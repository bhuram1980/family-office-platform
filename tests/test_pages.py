import pytest

from .conftest import static_get_routes


@pytest.mark.parametrize("prefix", ["/stocks", "/admin", "/family-office", "/deals", "/pevc", "/documents",
                                    "/philanthropy", "/tasks", "/real-estate", "/ir-portal"])
def test_every_page_renders(app, admin, prefix):
    routes = static_get_routes(app, prefix)
    assert routes
    bad = []
    for r in routes:
        res = admin.get(r)
        if res.status_code != 200:
            bad.append((r, res.status_code))
    assert not bad, bad


def test_tabs_render(admin):
    for tab in ["positions", "taxlots", "accounts", "margin", "performance", "details", "fundamentals", "comparison"]:
        r = admin.get(f"/stocks/holdings/?tab={tab}")
        assert r.status_code == 200
    for tab in ["all", "trades", "dividends", "interest", "cash"]:
        assert admin.get(f"/stocks/trade-log/?tab={tab}").status_code == 200


def test_edit_forms_render(app, admin):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.endswith("_edit"):
            # find one object id via the list page's model
            from app.crud import Resource
            for (aid, slug), res in Resource.registry.items():
                if res.endpoint("edit") == rule.endpoint:
                    obj = res.model.query.first()
                    if obj:
                        url = rule.rule.replace("<int:obj_id>", str(obj.id))
                        assert admin.get(url).status_code == 200, url

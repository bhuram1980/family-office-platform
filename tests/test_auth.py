from app.models import User, AuditLog
from app.extensions import db


def test_landing_public(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Pick an app" in r.data


def test_apps_require_login(client):
    r = client.get("/stocks/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_logout(client):
    r = client.login("tirumala")
    assert r.status_code == 302
    r = client.get("/stocks/")
    assert r.status_code == 200 and b"Portfolio Command Center" in r.data
    assert b"SUPER ADMIN" in r.data
    r = client.post("/logout")
    assert r.status_code == 302
    assert client.get("/stocks/").status_code == 302


def test_bad_password(client):
    r = client.login("tirumala", "nope")
    assert r.status_code == 200
    assert b"match, or the account is locked" in r.data


def test_csrf_enforced(client):
    r = client.c.post("/login", data={"username": "tirumala", "password": "bhuram-demo"})
    assert r.status_code == 400


def test_lockout_after_failures(app, client):
    for _ in range(5):
        client.login("noah", "wrong")
    u = User.query.filter_by(username="noah").first()
    assert u.locked
    assert client.login("noah").status_code == 200  # still refused
    u.locked = False
    db.session.commit()


def test_app_access_enforced(client):
    client.login("leah")  # investor: IR portal only
    assert client.get("/stocks/").status_code == 403
    assert client.get("/admin/users/").status_code == 403


def test_viewer_cannot_write(client):
    client.login("devon")
    r = client.post("/family-office/", {})
    assert r.status_code in (403, 405)


def test_single_sign_on_across_apps(admin):
    for path in ["/stocks/", "/admin/", "/family-office/", "/deals/", "/pevc/", "/documents/",
                 "/philanthropy/", "/tasks/", "/real-estate/", "/ir-portal/"]:
        assert admin.get(path).status_code == 200, path


def test_login_is_audited(admin):
    assert AuditLog.query.filter_by(action="login").count() > 0

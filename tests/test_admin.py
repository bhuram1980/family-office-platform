from app.extensions import db
from app.models import User, Announcement


def test_create_user_and_sign_in(admin, client):
    r = admin.post("/admin/users/new", {"name": "Test Person", "username": "tperson", "email": "tp@example.com",
                                         "role": "analyst", "app_tasks": "on", "active": "on", "password": "temp-password-1"})
    assert r.status_code == 302
    u = User.query.filter_by(username="tperson").first()
    assert u and u.must_change_pw and u.apps == ["tasks"]
    client.login("tperson", "temp-password-1")
    r = client.get("/tasks/")
    assert r.status_code == 302 and "/admin/profile" in r.headers["Location"]
    r = client.post("/admin/profile/", {"action": "password", "current": "temp-password-1", "new": "a-new-password-2", "confirm": "a-new-password-2"})
    assert r.status_code == 302
    assert client.get("/tasks/").status_code == 200
    assert client.get("/stocks/").status_code == 403


def test_admin_cannot_promote_to_super(client):
    client.login("priya")
    u = User.query.filter_by(username="sofia").first()
    r = client.post(f"/admin/users/{u.id}", {"name": u.name, "email": u.email, "role": "super_admin"})
    assert r.status_code == 403


def test_announcement_banner(admin):
    admin.post("/admin/announcements/new", {"title": "Banner test 123", "level": "info", "active": "on"})
    assert b"Banner test 123" in admin.get("/stocks/").data


def test_analyst_blocked_from_admin(client):
    client.login("marcus")
    assert client.get("/admin/users/").status_code == 403
    assert client.get("/admin/profile/").status_code == 200

import re

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


class Cfg(TestConfig):
    WTF_CSRF = True


@pytest.fixture(scope="session")
def app():
    app = create_app(Cfg)
    with app.app_context():
        from app.seed import run
        run(reset=True)
        yield app
        db.session.remove()


class Client:
    """Test client that carries the CSRF token like a browser form would."""

    def __init__(self, app):
        self.c = app.test_client()

    def token(self):
        with self.c.session_transaction() as s:
            if "_csrf" not in s:
                s["_csrf"] = "test-token"
            return s["_csrf"]

    @staticmethod
    def _fresh():
        # the session-wide app context is reused by test requests; drop the cached user
        from flask import g
        g.pop("_login_user", None)

    def get(self, *a, **kw):
        self._fresh()
        try:
            return self.c.get(*a, **kw)
        finally:
            self._fresh()

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        data.setdefault("csrf_token", self.token())
        self._fresh()
        try:
            return self.c.post(url, data=data, **kw)
        finally:
            self._fresh()

    def login(self, username, password="bhuram-demo"):
        return self.post("/login", {"username": username, "password": password})


@pytest.fixture()
def client(app):
    return Client(app)


@pytest.fixture()
def admin(app):
    c = Client(app)
    r = c.login("tirumala")
    assert r.status_code == 302
    return c


def static_get_routes(app, prefix):
    out = []
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and rule.rule.startswith(prefix) and not rule.rule.endswith(".csv"):
            out.append(rule.rule)
    return sorted(out)

import secrets
from datetime import datetime, date

from flask import Flask, abort, render_template, request, session, url_for, redirect
from flask_login import current_user

from .config import Config
from .extensions import db, migrate, login_manager
from . import filters
from .registry import APPS


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from . import models  # noqa: F401  (register models)
    from .models import User

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    filters.register(app)

    # ---------------- CSRF ----------------
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    @app.before_request
    def check_csrf():
        if request.method == "POST" and app.config.get("WTF_CSRF", True):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
            if not sent or sent != session.get("_csrf"):
                abort(400, "CSRF token missing or invalid")

    @app.context_processor
    def inject():
        from .badges import badge_count
        return dict(csrf_token=csrf_token, APPS=APPS, BRAND=app.config["BRAND"],
                    now=datetime.utcnow(), today=date.today(), badge_count=badge_count,
                    announcements_active=announcements_active)

    def qs(**kw):
        from urllib.parse import urlencode
        args = request.args.to_dict()
        for k, v in kw.items():
            if v is None:
                args.pop(k, None)
            else:
                args[k] = v
        return urlencode(args)

    app.jinja_env.globals["qs"] = qs
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["current_user"] = current_user
    app.jinja_env.globals["getattr_"] = lambda o, n: getattr(o, n, None)

    def announcements_active():
        from .models import Announcement
        if getattr(current_user, "role", None) == "investor":
            return []  # staff announcements are internal
        return Announcement.query.filter_by(active=True).order_by(Announcement.created_at.desc()).limit(2).all()

    # ---------------- blueprints ----------------
    from .blueprints import auth, admin, stocks, public
    app.register_blueprint(public.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp, url_prefix="/admin")
    app.register_blueprint(stocks.bp, url_prefix="/stocks")
    from .blueprints import register_optional
    register_optional(app)

    from .cli import register_cli
    register_cli(app)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, msg="You don't have access to this.", e=e), 403

    @app.errorhandler(404)
    def notfound(e):
        return render_template("error.html", code=404, msg="That page doesn't exist.", e=e), 404

    @app.errorhandler(400)
    def bad(e):
        return render_template("error.html", code=400, msg=getattr(e, "description", "Bad request"), e=e), 400

    @app.get("/favicon.ico")
    def favicon():
        return app.send_static_file("favicon.svg")

    @app.get("/healthz")
    def healthz():
        db.session.execute(db.text("select 1"))
        return {"ok": True}

    return app

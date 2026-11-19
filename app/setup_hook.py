"""One-time bootstrap endpoint for hosts where you cannot open a shell next to the database (e.g. Vercel).

It exists only while the SETUP_TOKEN environment variable is set. Remove the variable and redeploy
after use; without it the route is not registered at all.
"""
import hmac
import os

from flask import abort, jsonify, request

from .extensions import db

MIGRATIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


def register_setup(app):
    token = os.environ.get("SETUP_TOKEN", "")
    if len(token) < 32:
        return

    @app.post("/_setup")
    def bootstrap():
        sent = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(sent, token):
            abort(404)
        body = request.get_json(silent=True) or {}
        from flask_migrate import stamp, upgrade
        upgrade(directory=MIGRATIONS)
        done = ["migrated"]
        if body.get("seed"):
            from .seed import run
            run(reset=True)
            stamp(directory=MIGRATIONS)
            done.append("seeded")
        pw = body.get("passwords") or {}
        if pw:
            from .models import User
            n = 0
            for u in User.query.all():
                if u.username in pw and len(pw[u.username]) >= 16:
                    u.set_password(pw[u.username])
                    n += 1
            db.session.commit()
            done.append(f"passwords set for {n} users")
        return jsonify(ok=True, done=done)

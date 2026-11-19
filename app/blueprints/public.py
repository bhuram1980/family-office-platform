from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

from ..registry import APPS

bp = Blueprint("public", __name__)

SHARED = [
    ("Single sign-on", "key-round", "One account and one session across all ten apps. Roles and per-app access are set once in Admin."),
    ("One database cluster", "database", "Every app reads and writes the same PostgreSQL database, so a property, an entity or a deal is one row everywhere."),
    ("A shared assistant", "sparkles", "Scoring, filing suggestions and daily reviews run on the same rules engine and are logged in one audit trail."),
    ("Backups that restore", "archive-restore", "Nightly pg_dump with a restore drill script; the System page shows the last backup and row counts."),
    ("Deploy on every push", "rocket", "GitHub Actions runs the suite against a real Postgres service and the container deploys from main."),
    ("Tests that are tested", "flask-conical", "pytest covers auth, permissions and every write path; CI fails on any broken page in the shell."),
]


@bp.route("/")
def landing():
    return render_template("landing.html", shared=SHARED, apps=list(APPS.values()))


@bp.route("/launch")
def launch():
    if current_user.is_authenticated:
        first = current_user.apps[0] if current_user.apps else "admin"
        return redirect(url_for(first.replace("-", "_") + ".dashboard"))
    return redirect(url_for("auth.login"))

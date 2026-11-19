import importlib
import importlib.util

from flask import Blueprint, render_template

from .common import make_bp

OPTIONAL = ["family_office", "deals", "pevc", "documents", "philanthropy",
            "tasks", "real_estate", "ir_portal"]


def register_optional(app):
    """Register app blueprints that exist; stub the rest so the shell links resolve."""
    for mod in OPTIONAL:
        app_id = mod.replace("_", "-")
        if importlib.util.find_spec(f"{__name__}.{mod}") is not None:
            m = importlib.import_module(f".{mod}", __name__)
            app.register_blueprint(m.bp, url_prefix=f"/{app_id}")
        else:
            bp = make_bp(app_id, mod)

            @bp.route("/")
            def dashboard(_a=app_id):
                return render_template("placeholder.html")

            app.register_blueprint(bp, url_prefix=f"/{app_id}")

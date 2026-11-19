from functools import wraps

from flask import Blueprint, abort, g, redirect, request, url_for, jsonify
from flask_login import current_user

from ..registry import APPS

ACCOUNT_ENDPOINTS = {"admin.profile", "admin.notifications", "admin.passkeys"}


def make_bp(app_id, name=None):
    bp = Blueprint(name or app_id.replace("-", "_"), __name__)

    @bp.before_request
    def guard():
        g.app_id = app_id
        g.app = APPS[app_id]
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.full_path))
        if current_user.must_change_pw and request.endpoint != "admin.profile":
            return redirect(url_for("admin.profile", force=1))
        if request.endpoint in ACCOUNT_ENDPOINTS:
            return None
        if not current_user.can_access(app_id):
            abort(403)

    return bp


def write_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.can_write:
            abort(403)
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_admin:
            abort(403)
        return fn(*a, **kw)
    return wrapper


def wants_json():
    return request.headers.get("HX-Request") or request.accept_mimetypes.best == "application/json"

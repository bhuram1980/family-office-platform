"""Shared per-app settings page: a list of (key, label, default[, type]) stored in the settings table."""
from flask import abort, flash, redirect, request
from flask_login import current_user

from ..extensions import db
from ..models import Setting
from .audit import audit


def get(scope, key, default=None, cast=str):
    s = Setting.query.filter_by(scope=scope, key=key).first()
    raw = s.value if s and s.value not in (None, "") else default
    try:
        return cast(raw) if raw is not None else None
    except ValueError:
        return cast(default) if default is not None else None


def values(scope, keys):
    return {k[0]: get(scope, k[0], k[2]) for k in keys}


def handle(scope, keys):
    """Save the posted form when POST; returns a redirect or None."""
    if request.method != "POST":
        return None
    if not current_user.is_admin:
        abort(403)
    for k in keys:
        s = Setting.query.filter_by(scope=scope, key=k[0]).first() or Setting(scope=scope, key=k[0], label=k[1])
        s.value = request.form.get(k[0], "")
        db.session.add(s)
    audit(scope, "update", "settings", None, f"{scope} settings saved")
    db.session.commit()
    flash("Settings saved.", "success")
    return redirect(request.path)


def form_fields(scope, keys):
    vals = values(scope, keys)
    out = []
    for k in keys:
        typ = k[3] if len(k) > 3 else "text"
        if isinstance(typ, list):
            out.append((k[0], k[1], "select", [(o, o, o == vals[k[0]]) for o in typ]))
        else:
            out.append((k[0], k[1], typ, vals[k[0]]))
    return out

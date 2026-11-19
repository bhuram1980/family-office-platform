from flask import has_request_context
from flask_login import current_user
from ..extensions import db
from ..models import AuditLog


def audit(app, action, entity, entity_id=None, detail=None, user=None):
    uid = None
    if user is not None:
        uid = user.id
    elif has_request_context() and current_user and current_user.is_authenticated:
        uid = current_user.id
    db.session.add(AuditLog(user_id=uid, app=app, action=action, entity=entity,
                            entity_id=entity_id, detail=(detail or "")[:2000]))

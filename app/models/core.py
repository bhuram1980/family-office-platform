from datetime import datetime, date
from flask_login import UserMixin
from sqlalchemy import Numeric
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db

Money = Numeric(18, 2, asdecimal=False)

APP_IDS = ["stocks", "family-office", "deals", "pevc", "documents",
           "philanthropy", "tasks", "real-estate", "ir-portal", "admin"]
ROLES = ["super_admin", "admin", "analyst", "viewer", "investor"]


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="analyst")
    app_access = db.Column(db.String(400), nullable=False, default=",".join(APP_IDS))
    title = db.Column(db.String(120))
    color = db.Column(db.String(9), default="#6366f1")
    is_active_flag = db.Column(db.Boolean, default=True, nullable=False)
    locked = db.Column(db.Boolean, default=False, nullable=False)
    must_change_pw = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active(self):
        return self.is_active_flag and not self.locked

    @property
    def apps(self):
        if self.role == "super_admin":
            return list(APP_IDS)
        return [a for a in (self.app_access or "").split(",") if a]

    def can_access(self, app_id):
        return app_id in self.apps

    @property
    def can_write(self):
        return self.role in ("super_admin", "admin", "analyst")

    @property
    def is_admin(self):
        return self.role in ("super_admin", "admin")

    @property
    def initials(self):
        parts = self.name.split()
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

    @property
    def first_name(self):
        return self.name.split()[0]

    def __str__(self):
        return self.name


class LoginEvent(db.Model):
    __tablename__ = "login_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(64))
    success = db.Column(db.Boolean, default=True)
    ip = db.Column(db.String(64))
    user_agent = db.Column(db.String(300))
    at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user = db.relationship("User")


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    app = db.Column(db.String(40))
    action = db.Column(db.String(40))
    entity = db.Column(db.String(80))
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user = db.relationship("User")


class Announcement(TimestampMixin, db.Model):
    __tablename__ = "announcements"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    level = db.Column(db.String(20), default="info")
    active = db.Column(db.Boolean, default=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = db.relationship("User")


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    title = db.Column(db.String(200))
    body = db.Column(db.Text)
    link = db.Column(db.String(300))
    read = db.Column(db.Boolean, default=False)
    at = db.Column(db.DateTime, default=datetime.utcnow)


class ApiCredential(TimestampMixin, db.Model):
    __tablename__ = "api_credentials"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(120))
    key_hint = db.Column(db.String(20))
    scope = db.Column(db.String(200))
    expires_on = db.Column(db.Date)
    active = db.Column(db.Boolean, default=True)


class ApiUsage(db.Model):
    __tablename__ = "api_usage"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, index=True)
    provider = db.Column(db.String(80))
    app = db.Column(db.String(40))
    calls = db.Column(db.Integer, default=0)
    cost = db.Column(Money, default=0)


class Setting(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(40), default="platform")
    key = db.Column(db.String(80), nullable=False)
    value = db.Column(db.Text)
    label = db.Column(db.String(160))
    __table_args__ = (db.UniqueConstraint("scope", "key"),)


class EmailLog(db.Model):
    __tablename__ = "email_log"
    id = db.Column(db.Integer, primary_key=True)
    to_addr = db.Column(db.String(200))
    subject = db.Column(db.String(300))
    kind = db.Column(db.String(40))
    status = db.Column(db.String(20), default="sent")
    at = db.Column(db.DateTime, default=datetime.utcnow)


class Passkey(db.Model):
    __tablename__ = "passkeys"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    user = db.relationship("User")


def get_setting(key, default=None, scope="platform"):
    s = Setting.query.filter_by(scope=scope, key=key).first()
    return s.value if s else default

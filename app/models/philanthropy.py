"""Philanthropy: recipients, grants with approvals, tuition, DAF ledger and giving budgets."""
from datetime import date

from ..extensions import db
from .core import Money, TimestampMixin

GRANT_STATUSES = ["Requested", "Approved", "Paid", "Declined"]
CAUSES = ["Education", "Health", "Arts & culture", "Environment", "Community", "Faith", "Human services", "Research"]


class Recipient(TimestampMixin, db.Model):
    __tablename__ = "ph_recipients"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), default="Charity")  # Charity, School, Fund
    ein = db.Column(db.String(12))
    cause = db.Column(db.String(40))
    city = db.Column(db.String(80))
    contact = db.Column(db.String(120))
    email = db.Column(db.String(160))
    verified = db.Column(db.Boolean, default=True)  # 501(c)(3) status checked
    notes = db.Column(db.Text)

    def __str__(self):
        return self.name


class Grant(TimestampMixin, db.Model):
    __tablename__ = "ph_grants"
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("ph_recipients.id"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    requested_on = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(12), default="Requested", index=True)
    source = db.Column(db.String(20), default="DAF")  # DAF, Foundation, Personal
    purpose = db.Column(db.String(200))
    cause = db.Column(db.String(40))
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_on = db.Column(db.Date)
    paid_on = db.Column(db.Date)
    method = db.Column(db.String(12))  # Check, Wire, DAF grant
    reconciled = db.Column(db.Boolean, default=False)
    recipient = db.relationship("Recipient", backref="grants")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])

    def __str__(self):
        return f"{self.recipient.name if self.recipient else ''} ${self.amount or 0:,.0f}"


class Tuition(TimestampMixin, db.Model):
    __tablename__ = "ph_tuition"
    id = db.Column(db.Integer, primary_key=True)
    student = db.Column(db.String(120), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("ph_recipients.id"))
    term = db.Column(db.String(30))
    amount = db.Column(Money)
    due = db.Column(db.Date)
    paid_on = db.Column(db.Date)
    recipient = db.relationship("Recipient")


class DAFTxn(db.Model):
    __tablename__ = "ph_daf_txns"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(20))  # Contribution, Grant, Fee, Investment gain
    amount = db.Column(Money, nullable=False)
    memo = db.Column(db.String(200))
    grant_id = db.Column(db.Integer, db.ForeignKey("ph_grants.id", ondelete="SET NULL"))
    grant = db.relationship("Grant")


class GivingBudget(db.Model):
    __tablename__ = "ph_budgets"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    cause = db.Column(db.String(40), nullable=False)
    amount = db.Column(Money)

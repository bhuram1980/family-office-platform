"""IR Portal: co-investor profiles, positions in family-sponsored vehicles, offerings, documents and messages."""
from datetime import datetime

from sqlalchemy.orm import deferred

from ..extensions import db
from .core import Money, TimestampMixin


class InvestorProfile(TimestampMixin, db.Model):
    __tablename__ = "ir_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(30), default="LLC")  # Individual, Joint, LLC, Trust, IRA
    tax_id_last4 = db.Column(db.String(4))
    address = db.Column(db.String(200))
    bank_last4 = db.Column(db.String(4))
    accredited = db.Column(db.Boolean, default=True)
    user = db.relationship("User", backref="ir_profiles")

    def __str__(self):
        return self.name


class InvestorPosition(TimestampMixin, db.Model):
    __tablename__ = "ir_positions"
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("ir_profiles.id", ondelete="CASCADE"), index=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id"), nullable=False)
    ownership_pct = db.Column(db.Float, nullable=False)  # share of the family's position
    commitment = db.Column(Money)
    contributed = db.Column(Money)
    distributions = db.Column(Money, default=0)
    since = db.Column(db.Date)
    profile = db.relationship("InvestorProfile", backref=db.backref("positions", cascade="all, delete-orphan"))
    investment = db.relationship("Investment")

    @property
    def nav(self):
        return (self.investment.fmv or 0) * self.ownership_pct / 100

    @property
    def tvpi(self):
        return (self.nav + (self.distributions or 0)) / self.contributed if self.contributed else None


class IROffering(TimestampMixin, db.Model):
    __tablename__ = "ir_offerings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    deal_id = db.Column(db.Integer, db.ForeignKey("dl_deals.id", ondelete="SET NULL"))
    summary = db.Column(db.Text)
    asset_class = db.Column(db.String(40))
    location = db.Column(db.String(80))
    raise_amount = db.Column(Money)
    min_check = db.Column(Money)
    target_irr = db.Column(db.Float)
    target_close = db.Column(db.Date)
    status = db.Column(db.String(12), default="Open")  # Open, Closed
    deal = db.relationship("Deal")

    def __str__(self):
        return self.title


class IRInterest(TimestampMixin, db.Model):
    __tablename__ = "ir_interests"
    id = db.Column(db.Integer, primary_key=True)
    offering_id = db.Column(db.Integer, db.ForeignKey("ir_offerings.id", ondelete="CASCADE"), index=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("ir_profiles.id", ondelete="CASCADE"), index=True)
    amount = db.Column(Money)
    status = db.Column(db.String(12), default="Indicated")  # Indicated, Committed, Withdrawn
    offering = db.relationship("IROffering", backref="interests")
    profile = db.relationship("InvestorProfile")


class IRDocument(TimestampMixin, db.Model):
    __tablename__ = "ir_documents"
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("ir_profiles.id", ondelete="CASCADE"), index=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="SET NULL"))
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(30))  # Quarterly report, K-1, Capital call, Distribution, Subscription
    period = db.Column(db.String(10))
    content = deferred(db.Column(db.LargeBinary))
    viewed_at = db.Column(db.DateTime)
    profile = db.relationship("InvestorProfile", backref=db.backref("documents", cascade="all, delete-orphan"))
    investment = db.relationship("Investment")


class IRMessage(db.Model):
    __tablename__ = "ir_messages"
    id = db.Column(db.Integer, primary_key=True)
    investor_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=False)  # thread owner
    from_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    subject = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    at = db.Column(db.DateTime, default=datetime.utcnow)
    read_by_investor = db.Column(db.Boolean, default=False)
    read_by_office = db.Column(db.Boolean, default=False)
    investor = db.relationship("User", foreign_keys=[investor_id])
    sender = db.relationship("User", foreign_keys=[from_id])

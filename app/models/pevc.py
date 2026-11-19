"""PE / VC monitor: operating metrics, GP updates, document coverage and quarterly reviews on top of fo_investments."""
from datetime import date

from ..extensions import db
from .core import Money, TimestampMixin


class CompanyMetric(db.Model):
    __tablename__ = "pv_company_metrics"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), index=True, nullable=False)
    quarter = db.Column(db.String(7), nullable=False)  # 2026Q3
    revenue = db.Column(Money)
    ebitda = db.Column(Money)
    arr = db.Column(Money)
    cash = db.Column(Money)
    burn = db.Column(Money)
    headcount = db.Column(db.Integer)
    net_debt = db.Column(Money)
    investment = db.relationship("Investment", backref=db.backref("metrics", cascade="all, delete-orphan", order_by="CompanyMetric.quarter"))
    __table_args__ = (db.UniqueConstraint("investment_id", "quarter"),)

    @property
    def runway_months(self):
        return (self.cash or 0) / self.burn if self.burn and self.burn > 0 else None


class GPUpdate(TimestampMixin, db.Model):
    __tablename__ = "pv_updates"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), index=True)
    day = db.Column(db.Date, default=date.today)
    kind = db.Column(db.String(30), default="Quarterly letter")
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    sentiment = db.Column(db.String(10), default="Neutral")
    read = db.Column(db.Boolean, default=False)
    investment = db.relationship("Investment")


class PEDocument(TimestampMixin, db.Model):
    __tablename__ = "pv_documents"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), index=True)
    period = db.Column(db.String(7), nullable=False)
    kind = db.Column(db.String(40), nullable=False)  # Quarterly statement, Capital account, Financials, K-1
    received = db.Column(db.Date)
    filename = db.Column(db.String(200))
    investment = db.relationship("Investment")


class PEReview(TimestampMixin, db.Model):
    __tablename__ = "pv_reviews"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), index=True)
    quarter = db.Column(db.String(7), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    decision = db.Column(db.String(20), default="Hold")  # Hold, Watch, Exit, Add
    rating = db.Column(db.Integer)  # 1-5
    notes = db.Column(db.Text)
    investment = db.relationship("Investment")
    reviewer = db.relationship("User")

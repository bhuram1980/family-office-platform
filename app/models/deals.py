"""Deal Evaluator: screening pipeline, weighted scores, follow-ups, activity."""
from datetime import date, datetime

from ..extensions import db
from .core import Money, TimestampMixin

DEAL_STAGES = ["Inbox", "Screening", "Diligence", "IC Review", "Approved", "Closed", "Passed"]
CRITERIA = ["Team", "Market", "Terms", "Track record", "Downside protection", "Portfolio fit"]


class Deal(TimestampMixin, db.Model):
    __tablename__ = "dl_deals"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    sponsor = db.Column(db.String(120))
    asset_class = db.Column(db.String(40))
    sector = db.Column(db.String(60))
    location = db.Column(db.String(80))
    stage = db.Column(db.String(20), default="Inbox", index=True)
    size = db.Column(Money)  # total raise / EV
    check_size = db.Column(Money)  # our proposed check
    target_irr = db.Column(db.Float)
    target_moic = db.Column(db.Float)
    hold_years = db.Column(db.Float)
    source = db.Column(db.String(80))
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    received = db.Column(db.Date, default=date.today)
    decision_date = db.Column(db.Date)
    next_step = db.Column(db.String(200))
    thesis = db.Column(db.Text)
    risks = db.Column(db.Text)
    pass_reason = db.Column(db.String(200))
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id"))
    owner = db.relationship("User")
    investment = db.relationship("Investment")

    def __str__(self):
        return self.name


class DealScore(db.Model):
    __tablename__ = "dl_scores"
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey("dl_deals.id", ondelete="CASCADE"), index=True)
    criterion = db.Column(db.String(40), nullable=False)
    score = db.Column(db.Integer)
    note = db.Column(db.String(300))
    deal = db.relationship("Deal", backref=db.backref("scores", cascade="all, delete-orphan"))


class FollowUp(TimestampMixin, db.Model):
    __tablename__ = "dl_followups"
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey("dl_deals.id", ondelete="CASCADE"), index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    due = db.Column(db.Date)
    note = db.Column(db.String(300), nullable=False)
    done = db.Column(db.Boolean, default=False)
    deal = db.relationship("Deal", backref=db.backref("followups", cascade="all, delete-orphan"))
    owner = db.relationship("User")

    def __str__(self):
        return self.note


class DealActivity(db.Model):
    __tablename__ = "dl_activity"
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey("dl_deals.id", ondelete="CASCADE"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    at = db.Column(db.DateTime, default=datetime.utcnow)
    text = db.Column(db.String(400))
    deal = db.relationship("Deal", backref=db.backref("activity", cascade="all, delete-orphan", order_by="DealActivity.at.desc()"))
    user = db.relationship("User")

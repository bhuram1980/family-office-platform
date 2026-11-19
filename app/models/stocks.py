from datetime import datetime, date
from ..extensions import db
from .core import Money, TimestampMixin


class BrokerageAccount(TimestampMixin, db.Model):
    __tablename__ = "stk_accounts"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(20), nullable=False, unique=True)
    entity = db.Column(db.String(120))
    custodian = db.Column(db.String(80))
    acct_no = db.Column(db.String(30))
    kind = db.Column(db.String(40), default="Taxable")
    cash = db.Column(Money, default=0)
    margin_debt = db.Column(Money, default=0)
    margin_limit_pct = db.Column(db.Float, default=35.0)

    def __str__(self):
        return self.name


class Security(TimestampMixin, db.Model):
    __tablename__ = "stk_securities"
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(12), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    sector = db.Column(db.String(60))
    industry = db.Column(db.String(80))
    category = db.Column(db.String(40), default="Public Equity")
    theme = db.Column(db.String(60))
    price = db.Column(db.Float, default=0)
    prev_close = db.Column(db.Float, default=0)
    high_52w = db.Column(db.Float)
    low_52w = db.Column(db.Float)
    beta = db.Column(db.Float)
    pe = db.Column(db.Float)
    eps = db.Column(db.Float)
    div_yield = db.Column(db.Float, default=0)
    mkt_cap_b = db.Column(db.Float)
    revenue_growth = db.Column(db.Float)
    gross_margin = db.Column(db.Float)
    next_earnings = db.Column(db.Date)
    conviction = db.Column(db.Integer, default=3)
    stage = db.Column(db.String(20), default="Active")
    review_status = db.Column(db.String(20), default="None")
    reviewer = db.Column(db.String(60))
    next_review = db.Column(db.Date)

    @property
    def change_pct(self):
        return (self.price / self.prev_close - 1) * 100 if self.prev_close else 0

    @property
    def drawdown(self):
        return (self.price / self.high_52w - 1) * 100 if self.high_52w else 0

    def __str__(self):
        return self.ticker


class PriceBar(db.Model):
    __tablename__ = "stk_prices"
    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id", ondelete="CASCADE"), index=True)
    day = db.Column(db.Date, nullable=False)
    close = db.Column(db.Float, nullable=False)
    __table_args__ = (db.UniqueConstraint("security_id", "day"),)


class TaxLot(TimestampMixin, db.Model):
    __tablename__ = "stk_lots"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("stk_accounts.id"), index=True, nullable=False)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"), index=True, nullable=False)
    shares = db.Column(db.Float, nullable=False)
    cost_per_share = db.Column(db.Float, nullable=False)
    acquired = db.Column(db.Date, default=date.today)
    account = db.relationship("BrokerageAccount")
    security = db.relationship("Security")


class StockTxn(TimestampMixin, db.Model):
    __tablename__ = "stk_txns"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("stk_accounts.id"), index=True, nullable=False)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"))
    day = db.Column(db.Date, nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False)  # BUY SELL DIV INT DEP WD FEE
    shares = db.Column(db.Float)
    price = db.Column(db.Float)
    amount = db.Column(Money, default=0)
    fees = db.Column(Money, default=0)
    realized_pnl = db.Column(Money)
    note = db.Column(db.String(300))
    account = db.relationship("BrokerageAccount")
    security = db.relationship("Security")


class TradeProposal(TimestampMixin, db.Model):
    __tablename__ = "stk_proposals"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("stk_accounts.id"), nullable=False)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"), nullable=False)
    action = db.Column(db.String(10), nullable=False)  # BUY SELL TRIM ADD
    shares = db.Column(db.Float, nullable=False)
    limit_price = db.Column(db.Float)
    reason = db.Column(db.Text)
    status = db.Column(db.String(12), default="pending")
    proposed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    decided_at = db.Column(db.DateTime)
    account = db.relationship("BrokerageAccount")
    security = db.relationship("Security")
    proposed_by = db.relationship("User", foreign_keys=[proposed_by_id])
    decided_by = db.relationship("User", foreign_keys=[decided_by_id])


class OptionPosition(TimestampMixin, db.Model):
    __tablename__ = "stk_options"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("stk_accounts.id"), nullable=False)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"), nullable=False)
    right = db.Column(db.String(4), default="PUT")
    strike = db.Column(db.Float, nullable=False)
    expiry = db.Column(db.Date, nullable=False)
    contracts = db.Column(db.Integer, nullable=False)
    premium = db.Column(db.Float, nullable=False)
    mark = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(12), default="open")
    account = db.relationship("BrokerageAccount")
    security = db.relationship("Security")


class WatchItem(TimestampMixin, db.Model):
    __tablename__ = "stk_watchlist"
    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"), nullable=False)
    target_price = db.Column(db.Float)
    note = db.Column(db.String(300))
    security = db.relationship("Security")


class StockNote(TimestampMixin, db.Model):
    __tablename__ = "stk_notes"
    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"))
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    pinned = db.Column(db.Boolean, default=False)
    security = db.relationship("Security")
    author = db.relationship("User")


class Driver(TimestampMixin, db.Model):
    __tablename__ = "stk_drivers"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120))
    kind = db.Column(db.String(30))
    value = db.Column(db.Float)
    change_1d = db.Column(db.Float)
    zscore = db.Column(db.Float)


class DriverExposure(db.Model):
    __tablename__ = "stk_driver_exposure"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("stk_drivers.id", ondelete="CASCADE"))
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id", ondelete="CASCADE"))
    beta = db.Column(db.Float)
    driver = db.relationship("Driver")
    security = db.relationship("Security")


class MarketIndex(db.Model):
    __tablename__ = "stk_indices"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20))
    name = db.Column(db.String(60))
    value = db.Column(db.Float)
    change_pct = db.Column(db.Float)
    sort = db.Column(db.Integer, default=0)


class CorporateAction(TimestampMixin, db.Model):
    __tablename__ = "stk_actions"
    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(db.Integer, db.ForeignKey("stk_securities.id"), nullable=False)
    kind = db.Column(db.String(30))
    ex_date = db.Column(db.Date)
    detail = db.Column(db.String(300))
    status = db.Column(db.String(20), default="Pending")
    security = db.relationship("Security")


class ReviewSnapshot(db.Model):
    __tablename__ = "stk_review_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, index=True)
    ticker = db.Column(db.String(12))
    problems = db.Column(db.String(500))

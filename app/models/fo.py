"""Family Office ledger + Real Estate + PE/VC share these tables."""
from datetime import date, datetime

from ..extensions import db
from .core import Money, TimestampMixin

ASSET_CLASSES = ["Public Equities", "Real Estate", "Private Equity", "Venture Capital", "Private Credit", "Hedge Funds", "Alternative Investments"]


class Entity(TimestampMixin, db.Model):
    __tablename__ = "fo_entities"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    kind = db.Column(db.String(40))
    parent_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    ownership_pct = db.Column(db.Float, default=100.0)
    jurisdiction = db.Column(db.String(40))
    ein_hint = db.Column(db.String(12))
    formed = db.Column(db.Date)
    purpose = db.Column(db.String(300))
    manager = db.Column(db.String(120))
    parent = db.relationship("Entity", remote_side=[id], backref="children")

    def __str__(self):
        return self.name


class Investment(TimestampMixin, db.Model):
    __tablename__ = "fo_investments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    asset_class = db.Column(db.String(40), nullable=False)
    deal_type = db.Column(db.String(40))  # Fund, Co-Invest, Direct, Buyout, Growth, Early Stage
    sponsor = db.Column(db.String(120))
    sector = db.Column(db.String(60))
    vintage = db.Column(db.Integer)
    commitment = db.Column(Money, default=0)
    invested = db.Column(Money, default=0)  # called / paid-in
    fmv = db.Column(Money, default=0)
    distributions = db.Column(Money, default=0)
    status = db.Column(db.String(20), default="Active")
    marketable = db.Column(db.Boolean, default=False)
    city = db.Column(db.String(80))
    state = db.Column(db.String(4))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    target_irr = db.Column(db.Float)
    target_moic = db.Column(db.Float)
    hold_years = db.Column(db.Float)
    pref_return = db.Column(db.Float)
    promote = db.Column(db.Float)
    mgmt_fee = db.Column(db.Float)
    last_mark = db.Column(db.Date)
    sold_on = db.Column(db.Date)
    attention = db.Column(db.String(200))
    review_status = db.Column(db.String(20), default="Current")
    notes = db.Column(db.Text)
    entity = db.relationship("Entity")

    @property
    def total_value(self):
        return (self.fmv or 0) + (self.distributions or 0)

    @property
    def moic(self):
        return self.total_value / self.invested if self.invested else None

    @property
    def unfunded(self):
        return max(0, (self.commitment or 0) - (self.invested or 0))

    @property
    def gain(self):
        return self.total_value - (self.invested or 0)

    def __str__(self):
        return self.name


class Distribution(TimestampMixin, db.Model):
    __tablename__ = "fo_distributions"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False)
    amount = db.Column(Money, nullable=False)
    kind = db.Column(db.String(30), default="Income")
    tied_out = db.Column(db.Boolean, default=False)
    investment = db.relationship("Investment", backref=db.backref("distribution_rows", cascade="all, delete-orphan"))


class CapitalCall(TimestampMixin, db.Model):
    __tablename__ = "fo_capital_calls"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), nullable=False, index=True)
    notice_date = db.Column(db.Date)
    due = db.Column(db.Date, nullable=False)
    amount = db.Column(Money, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    investment = db.relationship("Investment", backref=db.backref("calls", cascade="all, delete-orphan"))


class Valuation(TimestampMixin, db.Model):
    __tablename__ = "fo_valuations"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False)
    fmv = db.Column(Money, nullable=False)
    method = db.Column(db.String(40), default="GP statement")
    note = db.Column(db.String(300))
    investment = db.relationship("Investment", backref=db.backref("valuations", cascade="all, delete-orphan"))


class Property(TimestampMixin, db.Model):
    __tablename__ = "re_properties"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id"))
    kind = db.Column(db.String(40))
    address = db.Column(db.String(200))
    city = db.Column(db.String(80))
    state = db.Column(db.String(4))
    metro = db.Column(db.String(80))
    units = db.Column(db.Integer)
    sqft = db.Column(db.Integer)
    purchase_price = db.Column(Money)
    acquired = db.Column(db.Date)
    fmv = db.Column(Money)
    ownership_pct = db.Column(db.Float, default=100.0)
    noi_t12 = db.Column(Money)
    revenue_t12 = db.Column(Money)
    opex_t12 = db.Column(Money)
    occupancy = db.Column(db.Float)
    capex_budget = db.Column(Money)
    cap_rate_uw = db.Column(db.Float)
    noi_uw = db.Column(Money)
    status = db.Column(db.String(20), default="Operating")
    manager = db.Column(db.String(120))
    entity = db.relationship("Entity")
    investment = db.relationship("Investment")

    @property
    def debt(self):
        return sum(l.balance or 0 for l in self.loans if l.direction == "payable")

    @property
    def equity(self):
        return (self.fmv or 0) - self.debt

    @property
    def ltv(self):
        return self.debt / self.fmv * 100 if self.fmv else None

    @property
    def debt_service(self):
        return sum(l.annual_debt_service or 0 for l in self.loans if l.direction == "payable")

    @property
    def dscr(self):
        return (self.noi_t12 or 0) / self.debt_service if self.debt_service else None

    @property
    def cap_rate(self):
        return (self.noi_t12 or 0) / self.fmv * 100 if self.fmv else None

    def __str__(self):
        return self.name


class PropertyMonth(db.Model):
    __tablename__ = "re_property_months"
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("re_properties.id", ondelete="CASCADE"), index=True)
    month = db.Column(db.Date, nullable=False)
    revenue = db.Column(Money)
    opex = db.Column(Money)
    noi = db.Column(Money)
    occupancy = db.Column(db.Float)
    reviewed = db.Column(db.Boolean, default=False)
    property = db.relationship("Property", backref=db.backref("months", cascade="all, delete-orphan", order_by="PropertyMonth.month"))


class Loan(TimestampMixin, db.Model):
    __tablename__ = "fo_loans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(40))  # Mortgage, Note receivable, Note payable, Line of credit, Intercompany
    direction = db.Column(db.String(12), default="payable")
    lender = db.Column(db.String(120))
    borrower = db.Column(db.String(120))
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    counterparty_entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    property_id = db.Column(db.Integer, db.ForeignKey("re_properties.id"))
    principal = db.Column(Money)
    balance = db.Column(Money)
    rate = db.Column(db.Float)
    rate_type = db.Column(db.String(20), default="Fixed")
    originated = db.Column(db.Date)
    maturity = db.Column(db.Date)
    annual_debt_service = db.Column(Money)
    dscr_covenant = db.Column(db.Float)
    status = db.Column(db.String(20), default="Current")
    entity = db.relationship("Entity", foreign_keys=[entity_id])
    counterparty_entity = db.relationship("Entity", foreign_keys=[counterparty_entity_id])
    property = db.relationship("Property", backref="loans")

    def __str__(self):
        return self.name


class Metro(TimestampMixin, db.Model):
    __tablename__ = "re_metros"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(8))
    pop_yoy = db.Column(db.Float)
    hpi_yoy = db.Column(db.Float)
    emp_yoy = db.Column(db.Float)
    permits_yoy = db.Column(db.Float)
    rent_yoy = db.Column(db.Float)
    score = db.Column(db.Integer)

    def __str__(self):
        return self.name


class REIssue(TimestampMixin, db.Model):
    __tablename__ = "re_issues"
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("re_properties.id", ondelete="CASCADE"))
    severity = db.Column(db.String(10), default="MEDIUM")
    rule = db.Column(db.String(40))
    title = db.Column(db.String(200))
    detail = db.Column(db.String(500))
    status = db.Column(db.String(20), default="Open")
    property = db.relationship("Property")


class Exchange1031(TimestampMixin, db.Model):
    __tablename__ = "re_exchanges"
    id = db.Column(db.Integer, primary_key=True)
    relinquished = db.Column(db.String(160), nullable=False)
    replacement = db.Column(db.String(160))
    sale_date = db.Column(db.Date)
    proceeds = db.Column(Money)
    qi = db.Column(db.String(120))
    status = db.Column(db.String(20), default="Identified")

    @property
    def id_deadline(self):
        from datetime import timedelta
        return self.sale_date + timedelta(days=45) if self.sale_date else None

    @property
    def close_deadline(self):
        from datetime import timedelta
        return self.sale_date + timedelta(days=180) if self.sale_date else None


class BankAccount(TimestampMixin, db.Model):
    __tablename__ = "fo_bank_accounts"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    institution = db.Column(db.String(80))
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    kind = db.Column(db.String(30), default="Operating")
    last4 = db.Column(db.String(4))
    balance = db.Column(Money, default=0)
    rate = db.Column(db.Float, default=0)
    min_balance = db.Column(Money, default=0)
    statement_balance = db.Column(Money)
    entity = db.relationship("Entity")

    def __str__(self):
        return f"{self.name} ··{self.last4 or ''}"


class CashTxn(TimestampMixin, db.Model):
    __tablename__ = "fo_cash_txns"
    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey("fo_bank_accounts.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    category = db.Column(db.String(60))
    counterparty = db.Column(db.String(160))
    memo = db.Column(db.String(300))
    reconciled = db.Column(db.Boolean, default=False)
    bank_account = db.relationship("BankAccount", backref="txns")


class Bill(TimestampMixin, db.Model):
    __tablename__ = "fo_bills"
    id = db.Column(db.Integer, primary_key=True)
    payee = db.Column(db.String(160), nullable=False)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    category = db.Column(db.String(60))
    amount = db.Column(Money, nullable=False)
    due = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="Open")
    paid_on = db.Column(db.Date)
    entity = db.relationship("Entity")


class RecurringCash(TimestampMixin, db.Model):
    __tablename__ = "fo_recurring_cash"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    direction = db.Column(db.String(4), default="out")
    amount = db.Column(Money, nullable=False)
    frequency = db.Column(db.String(20), default="Monthly")
    next_date = db.Column(db.Date)
    category = db.Column(db.String(60))
    active = db.Column(db.Boolean, default=True)
    entity = db.relationship("Entity")


class FamilyObligation(TimestampMixin, db.Model):
    __tablename__ = "fo_family_obligations"
    id = db.Column(db.Integer, primary_key=True)
    person = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(Money)
    frequency = db.Column(db.String(20), default="Monthly")
    next_date = db.Column(db.Date)
    paid_from = db.Column(db.String(120))


class Wire(TimestampMixin, db.Model):
    __tablename__ = "fo_wires"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, default=date.today)
    bank_account_id = db.Column(db.Integer, db.ForeignKey("fo_bank_accounts.id"))
    beneficiary = db.Column(db.String(160), nullable=False)
    bank = db.Column(db.String(120))
    amount = db.Column(Money, nullable=False)
    purpose = db.Column(db.String(300))
    status = db.Column(db.String(20), default="Draft")
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    bank_account = db.relationship("BankAccount")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])


class TreasuryHolding(TimestampMixin, db.Model):
    __tablename__ = "fo_treasuries"
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(160), nullable=False)
    cusip = db.Column(db.String(12))
    bank_account_id = db.Column(db.Integer, db.ForeignKey("fo_bank_accounts.id"))
    face = db.Column(Money)
    cost = db.Column(Money)
    yld = db.Column(db.Float)
    maturity = db.Column(db.Date)
    bank_account = db.relationship("BankAccount")


class SharedExpense(TimestampMixin, db.Model):
    __tablename__ = "fo_shared_expenses"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date)
    vendor = db.Column(db.String(160))
    description = db.Column(db.String(200))
    total = db.Column(Money)
    allocation = db.Column(db.String(300))  # "Entity A:60; Entity B:40"
    settled = db.Column(db.Boolean, default=False)

    def split(self):
        out = []
        for part in (self.allocation or "").split(";"):
            if ":" in part:
                n, p = part.rsplit(":", 1)
                try:
                    out.append((n.strip(), float(p)))
                except ValueError:
                    pass
        return out


class CloseTask(TimestampMixin, db.Model):
    __tablename__ = "fo_close_tasks"
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(7), nullable=False)  # YYYY-MM
    area = db.Column(db.String(60))
    task = db.Column(db.String(200), nullable=False)
    owner = db.Column(db.String(60))
    due = db.Column(db.Date)
    status = db.Column(db.String(20), default="Not started")
    bank_account_id = db.Column(db.Integer, db.ForeignKey("fo_bank_accounts.id"))
    book_balance = db.Column(Money)
    statement_balance = db.Column(Money)
    bank_account = db.relationship("BankAccount")


# ---- operations / legal / reports / tax
class InsurancePolicy(TimestampMixin, db.Model):
    __tablename__ = "fo_insurance"
    id = db.Column(db.Integer, primary_key=True)
    carrier = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(60))
    insured = db.Column(db.String(160))
    coverage = db.Column(Money)
    premium = db.Column(Money)
    renews = db.Column(db.Date)
    broker = db.Column(db.String(120))
    status = db.Column(db.String(20), default="Active")


class Vendor(TimestampMixin, db.Model):
    __tablename__ = "fo_vendors"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(60))
    contact = db.Column(db.String(120))
    email = db.Column(db.String(160))
    annual_spend = db.Column(Money)
    w9_on_file = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="Active")


class PersonalAsset(TimestampMixin, db.Model):
    __tablename__ = "fo_personal_assets"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(40))
    location = db.Column(db.String(120))
    owner = db.Column(db.String(120))
    value = db.Column(Money)
    appraised = db.Column(db.Date)
    insured = db.Column(db.Boolean, default=True)


class Contract(TimestampMixin, db.Model):
    __tablename__ = "fo_contracts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    counterparty = db.Column(db.String(160))
    kind = db.Column(db.String(60))
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    start = db.Column(db.Date)
    end = db.Column(db.Date)
    value = db.Column(Money)
    auto_renew = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="Active")
    entity = db.relationship("Entity")


class LegalDocument(TimestampMixin, db.Model):
    __tablename__ = "fo_legal_docs"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(60))
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    executed = db.Column(db.Date)
    location = db.Column(db.String(200))
    counsel = db.Column(db.String(120))
    next_review = db.Column(db.Date)
    entity = db.relationship("Entity")


class LegalMatter(TimestampMixin, db.Model):
    __tablename__ = "fo_legal_matters"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(60))
    counsel = db.Column(db.String(120))
    opened = db.Column(db.Date)
    exposure = db.Column(Money)
    budget = db.Column(Money)
    spent = db.Column(Money)
    status = db.Column(db.String(20), default="Open")
    next_step = db.Column(db.String(300))


class ReportRun(TimestampMixin, db.Model):
    __tablename__ = "fo_report_runs"
    id = db.Column(db.Integer, primary_key=True)
    report = db.Column(db.String(80), nullable=False)
    period = db.Column(db.String(20))
    generated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    recipients = db.Column(db.String(300))
    summary = db.Column(db.Text)
    status = db.Column(db.String(20), default="Draft")
    generated_by = db.relationship("User")


class TaxFiling(TimestampMixin, db.Model):
    __tablename__ = "fo_tax_filings"
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    form = db.Column(db.String(30), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    due = db.Column(db.Date)
    extended_to = db.Column(db.Date)
    preparer = db.Column(db.String(120))
    status = db.Column(db.String(20), default="Not started")
    entity = db.relationship("Entity")


class K1(TimestampMixin, db.Model):
    __tablename__ = "fo_k1s"
    id = db.Column(db.Integer, primary_key=True)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="CASCADE"))
    year = db.Column(db.Integer)
    expected = db.Column(db.Date)
    received = db.Column(db.Date)
    estimate = db.Column(db.Boolean, default=False)
    investment = db.relationship("Investment")


class EstimatedTax(TimestampMixin, db.Model):
    __tablename__ = "fo_estimated_tax"
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    jurisdiction = db.Column(db.String(30), default="Federal")
    quarter = db.Column(db.String(8))
    due = db.Column(db.Date)
    amount = db.Column(Money)
    paid_on = db.Column(db.Date)
    entity = db.relationship("Entity")


class ComplianceItem(TimestampMixin, db.Model):
    __tablename__ = "fo_compliance"
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id"))
    item = db.Column(db.String(200), nullable=False)
    authority = db.Column(db.String(80))
    due = db.Column(db.Date)
    status = db.Column(db.String(20), default="Pending")
    entity = db.relationship("Entity")

"""Documents: inbox, filing, e-signatures, requests, hiring paperwork and agent runs."""
import builtins
from datetime import datetime

from sqlalchemy.orm import deferred

from ..extensions import db
from .core import Money, TimestampMixin

DOC_KINDS = ["Capital call", "Distribution notice", "Quarterly statement", "Capital account", "K-1", "Bank statement", "Brokerage statement", "Invoice",
             "Contract", "Deal materials", "Insurance", "Tax", "Legal", "Property report", "Other"]


class InboundEmail(TimestampMixin, db.Model):
    __tablename__ = "dc_emails"
    id = db.Column(db.Integer, primary_key=True)
    from_addr = db.Column(db.String(200))
    subject = db.Column(db.String(300))
    body = db.Column(db.Text)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed = db.Column(db.Boolean, default=False)


class Document(TimestampMixin, db.Model):
    __tablename__ = "dc_documents"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    mime = db.Column(db.String(100))
    size = db.Column(db.Integer)
    content = deferred(db.Column(db.LargeBinary))
    text = db.Column(db.Text)
    source = db.Column(db.String(20), default="Upload")  # Upload, Email, Dropbox, Portal
    folder = db.Column(db.String(120))
    status = db.Column(db.String(20), default="Inbox", index=True)  # Inbox, Filed, Rejected
    kind = db.Column(db.String(40))
    proposed_kind = db.Column(db.String(40))
    proposed_app = db.Column(db.String(30))
    confidence = db.Column(db.Float)
    investment_id = db.Column(db.Integer, db.ForeignKey("fo_investments.id", ondelete="SET NULL"))
    entity_id = db.Column(db.Integer, db.ForeignKey("fo_entities.id", ondelete="SET NULL"))
    property_id = db.Column(db.Integer, db.ForeignKey("re_properties.id", ondelete="SET NULL"))
    deal_id = db.Column(db.Integer, db.ForeignKey("dl_deals.id", ondelete="SET NULL"))
    email_id = db.Column(db.Integer, db.ForeignKey("dc_emails.id", ondelete="SET NULL"))
    period = db.Column(db.String(10))
    amount = db.Column(Money)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    filed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    filed_at = db.Column(db.DateTime)
    flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(200))
    deleted_at = db.Column(db.DateTime)
    investment = db.relationship("Investment")
    entity = db.relationship("Entity")
    property = db.relationship("Property")
    deal = db.relationship("Deal", backref="documents")
    email = db.relationship("InboundEmail", backref="attachments")
    filed_by = db.relationship("User")

    @builtins.property
    def target(self):
        return self.investment or self.property or self.deal or self.entity

    def __str__(self):
        return self.filename


class SignatureRequest(TimestampMixin, db.Model):
    __tablename__ = "dc_signatures"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("dc_documents.id", ondelete="SET NULL"))
    status = db.Column(db.String(20), default="Draft")  # Draft, Sent, Signed, Declined, Voided
    sent_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    message = db.Column(db.String(400))
    document = db.relationship("Document")
    created_by = db.relationship("User")

    def __str__(self):
        return self.title


class Signer(db.Model):
    __tablename__ = "dc_signers"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("dc_signatures.id", ondelete="CASCADE"), index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160))
    order = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="Pending")  # Pending, Delivered, Signed, Declined
    signed_at = db.Column(db.DateTime)
    request = db.relationship("SignatureRequest", backref=db.backref("signers", cascade="all, delete-orphan", order_by="Signer.order"))


class DocRequest(TimestampMixin, db.Model):
    __tablename__ = "dc_requests"
    id = db.Column(db.Integer, primary_key=True)
    what = db.Column(db.String(200), nullable=False)
    from_party = db.Column(db.String(160))
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    requested_on = db.Column(db.Date)
    due = db.Column(db.Date)
    status = db.Column(db.String(20), default="Requested")  # Requested, Received, Overdue, Canceled
    document_id = db.Column(db.Integer, db.ForeignKey("dc_documents.id", ondelete="SET NULL"))
    owner = db.relationship("User")
    document = db.relationship("Document")

    def __str__(self):
        return self.what


class Candidate(TimestampMixin, db.Model):
    __tablename__ = "dc_candidates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120))
    stage = db.Column(db.String(20), default="Screen")  # Screen, Interview, Offer, Hired, Declined
    resume = db.Column(db.Boolean, default=False)
    offer_letter = db.Column(db.String(20), default="—")
    background_check = db.Column(db.String(20), default="—")
    i9 = db.Column(db.Boolean, default=False)
    start_date = db.Column(db.Date)


class AgentRun(db.Model):
    __tablename__ = "dc_agent_runs"
    id = db.Column(db.Integer, primary_key=True)
    agent = db.Column(db.String(60), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed = db.Column(db.Integer, default=0)
    filed = db.Column(db.Integer, default=0)
    errors = db.Column(db.Integer, default=0)
    note = db.Column(db.String(300))

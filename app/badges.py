"""Sidebar badge counters. Apps register a callable per key."""
from datetime import date

BADGES = {}


def badge(key):
    def deco(fn):
        BADGES[key] = fn
        return fn
    return deco


def badge_count(key):
    fn = BADGES.get(key)
    if not fn:
        return 0
    try:
        return fn()
    except Exception:
        return 0


@badge("proposals")
def _proposals():
    from .models import TradeProposal
    return TradeProposal.query.filter_by(status="pending").count()


@badge("watch")
def _watch():
    from .models import WatchItem
    return WatchItem.query.count()


@badge("re_issues")
def _re_issues():
    from .models import REIssue
    return REIssue.query.filter_by(status="Open", severity="HIGH").count()


@badge("pevc_unread")
def _pevc_unread():
    from .models import GPUpdate
    return GPUpdate.query.filter_by(read=False).count()


@badge("pevc_attention")
def _pevc_attention():
    from .blueprints.pevc import attention_items
    return len(attention_items())


@badge("tasks_mine")
def _tasks_mine():
    from flask_login import current_user
    from .models import Task
    return Task.query.filter(Task.deleted_at.is_(None), Task.assignee_id == current_user.id, Task.status.notin_(["Done", "Canceled"])).count()


@badge("deal_followups")
def _deal_followups():
    from .models import FollowUp
    return FollowUp.query.filter(FollowUp.done.is_(False), FollowUp.due <= date.today()).count()


@badge("doc_inbox")
def _doc_inbox():
    from .models import Document
    return Document.query.filter(Document.deleted_at.is_(None), Document.status == "Inbox").count()


@badge("doc_flags")
def _doc_flags():
    from .models import Document
    return Document.query.filter(Document.deleted_at.is_(None), Document.flagged.is_(True)).count()


@badge("ph_requests")
def _ph_requests():
    from .models import Grant
    return Grant.query.filter_by(status="Requested").count()


@badge("ir_msgs")
def _ir_msgs():
    from flask_login import current_user
    from .models import IRMessage
    if current_user.role == "investor":
        return IRMessage.query.filter_by(investor_id=current_user.id, read_by_investor=False).count()
    return IRMessage.query.filter_by(read_by_office=False).count()


@badge("ir_docs")
def _ir_docs():
    from flask_login import current_user
    from .models import InvestorProfile, IRDocument
    if current_user.role != "investor":
        return 0
    return IRDocument.query.join(InvestorProfile).filter(InvestorProfile.user_id == current_user.id, IRDocument.viewed_at.is_(None)).count()

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

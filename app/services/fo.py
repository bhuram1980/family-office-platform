"""Cross-app figures for the Family Office ledger."""
from collections import defaultdict
from datetime import date, timedelta

from ..extensions import db
from ..models import (BankAccount, Bill, BrokerageAccount, CapitalCall, Distribution, Entity, Investment, Loan,
                      PersonalAsset, Property, RecurringCash, TreasuryHolding)
from . import portfolio as pf


def sync_public_sleeves():
    """Public-equity sleeves in the ledger take their value from the Stocks app (same database)."""
    by_entity = defaultdict(float)
    for p in pf.positions(by_account=True):
        a = next(iter(p.accounts))
        by_entity[a.entity] += p.mv
    for a in BrokerageAccount.query.all():
        by_entity[a.entity] += (a.cash or 0) - (a.margin_debt or 0)
    sleeves = Investment.query.filter_by(asset_class="Public Equities").all()
    names = {s.entity.name: s for s in sleeves if s.entity}
    leftover = 0.0
    for ent, v in by_entity.items():
        if ent in names:
            names[ent].fmv = round(v, 2)
        else:
            leftover += v
    if sleeves and leftover:
        sleeves[-1].fmv = round((sleeves[-1].fmv or 0) + leftover, 2)
    db.session.commit()


def active_investments():
    return Investment.query.filter(Investment.status == "Active").all()


def allocation(invs=None):
    invs = invs or active_investments()
    out = defaultdict(lambda: dict(n=0, invested=0.0, fmv=0.0, dist=0.0))
    for i in invs:
        r = out[i.asset_class]
        r["n"] += 1
        r["invested"] += i.invested or 0
        r["fmv"] += i.fmv or 0
        r["dist"] += i.distributions or 0
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["fmv"]))


def cash_total():
    return sum(b.balance or 0 for b in BankAccount.query.all())


def treasury_total():
    return sum(t.cost or 0 for t in TreasuryHolding.query.all())


def monthly_burn():
    out = 0.0
    for r in RecurringCash.query.filter_by(active=True, direction="out").all():
        f = {"Monthly": 1, "Semi-monthly": 2, "Quarterly": 1 / 3, "Semi-annual": 1 / 6, "Annual": 1 / 12}.get(r.frequency, 1)
        out += (r.amount or 0) * f
    return out


def alerts():
    today = date.today()
    items = []
    for b in Bill.query.filter(Bill.status != "Paid").order_by(Bill.due).all():
        days = (b.due - today).days
        if days < 0:
            items.append(("danger", f"Bill overdue: {b.payee}", f"Past due by {-days} days — ${b.amount:,.0f}"))
        elif days <= 7:
            items.append(("warn", f"Bill due: {b.payee}", f"Due in {days} days — ${b.amount:,.0f}"))
    for l in Loan.query.filter(Loan.maturity <= today + timedelta(days=120)).all():
        items.append(("warn", f"Loan maturing: {l.name}", f"Matures {l.maturity:%b %d, %Y} — balance ${l.balance:,.0f}"))
    for c in CapitalCall.query.filter_by(status="Pending").filter(CapitalCall.due <= today + timedelta(days=14)).all():
        items.append(("info", f"Capital call: {c.investment.name}", f"${c.amount:,.0f} due {c.due:%b %d}"))
    for p in Property.query.all():
        if p.dscr and p.loans and p.dscr < max(l.dscr_covenant or 0 for l in p.loans) + 0.15:
            items.append(("danger", f"DSCR near covenant: {p.name}", f"DSCR {p.dscr:.2f}x"))
    order = {"danger": 0, "warn": 1, "info": 2}
    return sorted(items, key=lambda x: order[x[0]])


def net_worth():
    invs = active_investments()
    inv_fmv = sum(i.fmv or 0 for i in invs if i.asset_class != "Real Estate")
    re_equity = sum(i.fmv or 0 for i in invs if i.asset_class == "Real Estate")
    cash = cash_total()
    personal = sum(a.value or 0 for a in PersonalAsset.query.all())
    receivables = sum(l.balance or 0 for l in Loan.query.filter_by(direction="receivable").filter(Loan.kind != "Intercompany").all())
    liabilities = sum(l.balance or 0 for l in Loan.query.filter_by(direction="payable").filter(Loan.property_id.is_(None)).all())
    payables = sum(b.amount or 0 for b in Bill.query.filter(Bill.status != "Paid").all())
    assets = inv_fmv + re_equity + cash + personal + receivables
    return dict(inv_fmv=inv_fmv, re_equity=re_equity, cash=cash, personal=personal, receivables=receivables,
                liabilities=liabilities, payables=payables, assets=assets, net=assets - liabilities - payables)

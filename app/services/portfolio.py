"""Portfolio maths for the Stocks app: positions from tax lots, trades, returns, health."""
import random
from collections import defaultdict
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import (BrokerageAccount, MarketIndex, PriceBar, Security, StockTxn,
                      TaxLot, Driver)
from .audit import audit

BENCH = "SPX"


class Pos:
    __slots__ = ("security", "accounts", "shares", "cost", "lots")

    def __init__(self, security):
        self.security = security
        self.accounts = set()
        self.shares = 0.0
        self.cost = 0.0
        self.lots = []

    @property
    def avg_cost(self):
        return self.cost / self.shares if self.shares else 0

    @property
    def mv(self):
        return self.shares * self.security.price

    @property
    def pnl(self):
        return self.mv - self.cost

    @property
    def pnl_pct(self):
        return (self.pnl / self.cost * 100) if self.cost else 0

    @property
    def day_pnl(self):
        return self.shares * (self.security.price - (self.security.prev_close or self.security.price))


def positions(account_ids=None, by_account=False):
    q = TaxLot.query.join(Security).filter(TaxLot.shares > 0)
    if account_ids:
        q = q.filter(TaxLot.account_id.in_(account_ids))
    out = {}
    for lot in q.all():
        key = (lot.account_id, lot.security_id) if by_account else lot.security_id
        p = out.get(key)
        if not p:
            p = out[key] = Pos(lot.security)
        p.accounts.add(lot.account)
        p.shares += lot.shares
        p.cost += lot.shares * lot.cost_per_share
        p.lots.append(lot)
    res = sorted(out.values(), key=lambda p: -p.mv)
    return res


def totals(account_ids=None):
    pos = positions(account_ids)
    accts = BrokerageAccount.query.all() if not account_ids else BrokerageAccount.query.filter(BrokerageAccount.id.in_(account_ids)).all()
    long_mv = sum(p.mv for p in pos)
    cost = sum(p.cost for p in pos)
    cash = sum(a.cash or 0 for a in accts)
    margin = sum(a.margin_debt or 0 for a in accts)
    by_cat = defaultdict(float)
    for p in pos:
        by_cat[p.security.category or "Public Equity"] += p.mv
    day = sum(p.day_pnl for p in pos)
    return dict(positions=pos, long_mv=long_mv, cost=cost, unrealized=long_mv - cost,
                unrealized_pct=((long_mv - cost) / cost * 100) if cost else 0,
                cash=cash, margin=margin, cash_net=cash - margin, net=long_mv + cash - margin,
                by_cat=dict(by_cat), day_pnl=day, accounts=accts, lots=sum(len(p.lots) for p in pos),
                margin_use=(margin / long_mv * 100) if long_mv else 0)


def price_matrix(security_ids, since):
    rows = (db.session.query(PriceBar.security_id, PriceBar.day, PriceBar.close)
            .filter(PriceBar.security_id.in_(security_ids), PriceBar.day >= since)
            .order_by(PriceBar.day).all())
    m = defaultdict(dict)
    for sid, d, c in rows:
        m[sid][d] = c
    return m


def value_series(pos, days=365):
    """Holdings-weighted value series using today's share counts (constant-holdings return)."""
    since = date.today() - timedelta(days=days + 5)
    sids = [p.security.id for p in pos]
    m = price_matrix(sids, since)
    all_days = sorted({d for s in m.values() for d in s})
    series = []
    last = {}
    for d in all_days:
        v = 0
        for p in pos:
            c = m[p.security.id].get(d, last.get(p.security.id))
            if c is None:
                c = p.security.price
            last[p.security.id] = c
            v += c * p.shares
        series.append((d, v))
    return series


def bench_series(days=365):
    b = Security.query.filter_by(ticker=BENCH).first()
    if not b:
        return []
    since = date.today() - timedelta(days=days + 5)
    return [(r.day, r.close) for r in PriceBar.query.filter(PriceBar.security_id == b.id, PriceBar.day >= since).order_by(PriceBar.day)]


def period_returns(series):
    if not series:
        return {}
    today = series[-1][0]
    last = series[-1][1]
    marks = {"1D": today - timedelta(days=1), "1W": today - timedelta(days=7), "1M": today - timedelta(days=30),
             "3M": today - timedelta(days=91), "6M": today - timedelta(days=182), "YTD": date(today.year, 1, 1) - timedelta(days=1),
             "1Y": today - timedelta(days=365)}
    out = {}
    for k, d in marks.items():
        base = None
        for dd, v in series:
            if dd <= d:
                base = v
            else:
                break
        if base is None:
            base = series[0][1]
        out[k] = (last / base - 1) * 100 if base else 0
    if len(series) > 1:
        out["1D"] = (series[-1][1] / series[-2][1] - 1) * 100
    return out


# ---------------------------------------------------------------- trading
def execute_trade(account, security, side, shares, price, user=None, note=None, fees=0.0, day=None):
    side = side.upper()
    day = day or date.today()
    shares = float(shares)
    price = float(price)
    if shares <= 0 or price <= 0:
        raise ValueError("Shares and price must be positive")
    if side in ("BUY", "ADD"):
        cost = shares * price + fees
        account.cash = (account.cash or 0) - cost
        if account.cash < 0:  # draw on margin
            account.margin_debt = (account.margin_debt or 0) - account.cash
            account.cash = 0
        db.session.add(TaxLot(account=account, security=security, shares=shares, cost_per_share=price, acquired=day))
        txn = StockTxn(account=account, security=security, day=day, kind="BUY", shares=shares, price=price,
                       amount=-shares * price, fees=fees, note=note)
    elif side in ("SELL", "TRIM"):
        lots = (TaxLot.query.filter_by(account_id=account.id, security_id=security.id)
                .filter(TaxLot.shares > 0).order_by(TaxLot.acquired).all())
        held = sum(l.shares for l in lots)
        if shares > held + 1e-9:
            raise ValueError(f"Only {held:,.0f} shares of {security.ticker} held in {account.name}")
        left = shares
        realized = 0.0
        for l in lots:
            take = min(l.shares, left)
            realized += take * (price - l.cost_per_share)
            l.shares -= take
            left -= take
            if l.shares <= 1e-9:
                db.session.delete(l)
            if left <= 1e-9:
                break
        proceeds = shares * price - fees
        pay = min(account.margin_debt or 0, proceeds)
        account.margin_debt = (account.margin_debt or 0) - pay
        account.cash = (account.cash or 0) + proceeds - pay
        txn = StockTxn(account=account, security=security, day=day, kind="SELL", shares=shares, price=price,
                       amount=shares * price, fees=fees, realized_pnl=realized - fees, note=note)
    else:
        raise ValueError("Unknown side")
    db.session.add(txn)
    audit("stocks", "trade", "stk_txns", None, f"{side} {shares:,.0f} {security.ticker} @ {price:,.2f} in {account.code}", user=user)
    return txn


def refresh_prices(seed=None):
    """Simulated market tick: moves every price by a small random amount and stores today's bar."""
    rnd = random.Random(seed)
    today = date.today()
    for s in Security.query.all():
        last_bar = PriceBar.query.filter(PriceBar.security_id == s.id, PriceBar.day < today).order_by(PriceBar.day.desc()).first()
        base = last_bar.close if last_bar else s.price
        s.prev_close = base
        vol = 0.008 if s.ticker == BENCH else 0.018 * (s.beta or 1)
        s.price = round(max(0.5, s.price * (1 + rnd.gauss(0.0004, vol))), 2)
        s.high_52w = max(s.high_52w or s.price, s.price)
        s.low_52w = min(s.low_52w or s.price, s.price)
        bar = PriceBar.query.filter_by(security_id=s.id, day=today).first()
        if bar:
            bar.close = s.price
        else:
            db.session.add(PriceBar(security_id=s.id, day=today, close=s.price))
    for i in MarketIndex.query.all():
        ch = rnd.gauss(0.02, 0.6)
        i.value = round(i.value * (1 + ch / 100), 2)
        i.change_pct = round(ch, 2)
    for d in Driver.query.all():
        d.change_1d = round(rnd.gauss(0, 2.5), 2)
        d.zscore = round(abs(d.change_1d) / 1.3, 1)
    audit("stocks", "refresh", "prices", None, "Simulated price refresh")


# ---------------------------------------------------------------- health
MEASURES = [
    ("Drawdown", "Price is more than 25% below its 52-week high."),
    ("Underwater", "Position is more than 20% below its cost basis."),
    ("Concentration", "Position is more than 6% of long market value."),
    ("Momentum", "Price fell more than 10% over the last month."),
    ("Valuation", "P/E above 60 with revenue growth under 15%."),
    ("Earnings soon", "Reports earnings within the next 7 days."),
    ("Low conviction", "Conviction score of 1 or 2 on the review board."),
]


def problems_for(p, long_mv, month_ago_price=None):
    s = p.security
    out, strengths = [], []
    if s.drawdown < -25:
        out.append("Drawdown")
    if p.pnl_pct < -20:
        out.append("Underwater")
    if long_mv and p.mv / long_mv > 0.06:
        out.append("Concentration")
    if month_ago_price and (s.price / month_ago_price - 1) < -0.10:
        out.append("Momentum")
    if (s.pe or 0) > 60 and (s.revenue_growth or 0) < 15:
        out.append("Valuation")
    if s.next_earnings and 0 <= (s.next_earnings - date.today()).days <= 7:
        out.append("Earnings soon")
    if (s.conviction or 3) <= 2:
        out.append("Low conviction")
    if p.pnl_pct > 50:
        strengths.append("Big winner")
    if month_ago_price and (s.price / month_ago_price - 1) > 0.08:
        strengths.append("Momentum")
    if (s.conviction or 0) >= 4:
        strengths.append("High conviction")
    if (s.revenue_growth or 0) > 25:
        strengths.append("Fast growth")
    return out, strengths

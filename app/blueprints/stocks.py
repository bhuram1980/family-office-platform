from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..crud import Field, Resource
from ..extensions import db
from ..models import (BrokerageAccount, CorporateAction, Driver, DriverExposure, MarketIndex, OptionPosition,
                      PriceBar, ReviewSnapshot, Security, Setting, StockNote, StockTxn, TaxLot, TradeProposal,
                      WatchItem, User)
from ..services import portfolio as pf
from ..services.audit import audit
from .common import make_bp, write_required

bp = make_bp("stocks")

SECTORS = ["Technology", "Communication", "Consumer Discretionary", "Consumer Staples", "Financials", "Health Care", "Energy",
           "Utilities", "Industrials", "Materials", "Real Estate", "Cash", "Commodities", "Alternatives"]
CATS = ["Public Equity", "Money Market", "Alternative Inv.", "Other Inv."]

Resource("stocks", "securities", Security, "Securities", [
    Field("ticker", required=True), Field("name", required=True),
    Field("sector", type="select", choices=SECTORS), Field("theme"), Field("category", type="select", choices=CATS),
    Field("price", type="float", required=True), Field("prev_close", "Prev close", type="float", list=False),
    Field("high_52w", "52w high", type="float", list=False), Field("low_52w", "52w low", type="float", list=False),
    Field("beta", type="float"), Field("pe", "P/E", type="float"), Field("div_yield", "Div yield %", type="float"),
    Field("revenue_growth", "Rev growth %", type="float", list=False), Field("next_earnings", type="date"),
    Field("conviction", type="select", choices=[1, 2, 3, 4, 5], list=False),
    Field("stage", type="select", choices=["Active", "Watch", "Exited", "Benchmark"]),
], singular="Security", order_by=Security.ticker, filters=["stage"], search=["ticker", "name", "theme"]).register(bp)

Resource("stocks", "accounts", BrokerageAccount, "Brokerage accounts", [
    Field("name", required=True), Field("code", required=True), Field("entity"), Field("custodian"), Field("acct_no", "Account #"),
    Field("kind", type="select", choices=["Taxable", "Taxable · Margin", "Tax-exempt", "Retirement"]),
    Field("cash", type="money"), Field("margin_debt", type="money"), Field("margin_limit_pct", "Margin limit %", type="float"),
], singular="Account", order_by=BrokerageAccount.id).register(bp)

Resource("stocks", "watch", WatchItem, "Watchlist items", [
    Field("security_id", "Security", type="fk", fk=Security, fk_label=lambda s: f"{s.ticker} — {s.name}", required=True),
    Field("target_price", type="float"), Field("note"),
], singular="Watchlist item", nav="stocks.watchlist").register(bp)

Resource("stocks", "note", StockNote, "Notes", [
    Field("title", required=True),
    Field("security_id", "Security", type="fk", fk=Security, fk_label=lambda s: s.ticker),
    Field("body", type="text", list=False), Field("pinned", type="bool"),
], singular="Note", nav="stocks.notes").register(bp)

Resource("stocks", "option", OptionPosition, "Option positions", [
    Field("account_id", "Account", type="fk", fk=BrokerageAccount, required=True),
    Field("security_id", "Underlying", type="fk", fk=Security, fk_label=lambda s: s.ticker, required=True),
    Field("right", type="select", choices=["PUT", "CALL"]), Field("strike", type="float", required=True),
    Field("expiry", type="date", required=True), Field("contracts", type="int", required=True, help="Negative for short"),
    Field("premium", type="float", required=True), Field("mark", type="float", required=True),
    Field("status", type="select", choices=["open", "closed", "expired", "assigned"]),
], singular="Option", nav="stocks.options").register(bp)

Resource("stocks", "corporate-actions", CorporateAction, "Corporate actions", [
    Field("security_id", "Security", type="fk", fk=Security, fk_label=lambda s: s.ticker, required=True),
    Field("kind", type="select", choices=["Dividend", "Special dividend", "Split", "Spin-off", "Merger", "Tender"]),
    Field("ex_date", type="date"), Field("detail"), Field("status", type="select", choices=["Pending", "Processed", "Ignored"]),
], singular="Corporate action", nav="stocks.dashboard").register(bp)


@bp.app_context_processor
def stocks_ctx():
    return {"market_indices": lambda: MarketIndex.query.order_by(MarketIndex.sort).all()}


def selected_accounts():
    codes = [c for c in request.args.get("acct", "").split(",") if c]
    if not codes:
        return None, []
    accts = BrokerageAccount.query.filter(BrokerageAccount.code.in_(codes)).all()
    return [a.id for a in accts], codes


def month_ago_prices(sids):
    d = date.today() - timedelta(days=30)
    rows = (db.session.query(PriceBar.security_id, PriceBar.close).filter(PriceBar.security_id.in_(sids), PriceBar.day <= d)
            .order_by(PriceBar.security_id, PriceBar.day.desc()).distinct(PriceBar.security_id).all())
    return dict(rows)


# ------------------------------------------------------------------ dashboard
@bp.route("/")
def dashboard():
    t = pf.totals()
    pos = t["positions"]
    series = pf.value_series(pos, 380)
    bench = pf.bench_series(380)
    rets = pf.period_returns(series)
    brets = pf.period_returns(bench)
    movers = sorted(pos, key=lambda p: p.pnl_pct)
    proposals = TradeProposal.query.filter_by(status="pending").order_by(TradeProposal.created_at).all()
    # P&L histogram
    buckets = [("< -20%", -1e9, -20), ("-20 to -10%", -20, -10), ("-10 to 0%", -10, 0), ("0 to 20%", 0, 20), ("20 to 50%", 20, 50), ("50 to 100%", 50, 100), ("> 100%", 100, 1e9)]
    hist = [sum(1 for p in pos if lo <= p.pnl_pct < hi) for _, lo, hi in buckets]
    drivers = Driver.query.order_by(db.func.abs(Driver.change_1d).desc()).limit(6).all()
    affected = dict(db.session.query(DriverExposure.driver_id, db.func.count()).group_by(DriverExposure.driver_id).all())
    conv = defaultdict(int)
    for p in pos:
        conv[p.security.conviction or 3] += 1
    earnings = sorted([p for p in pos if p.security.next_earnings and p.security.next_earnings >= date.today()],
                      key=lambda p: p.security.next_earnings)[:20]
    recent_txns = StockTxn.query.order_by(StockTxn.day.desc(), StockTxn.id.desc()).limit(12).all()
    notes = StockNote.query.order_by(StockNote.created_at.desc()).limit(8).all()
    actions = CorporateAction.query.order_by(CorporateAction.ex_date.desc()).limit(8).all()
    chart_series = series[-130:]
    bench_map = dict(bench)
    b0 = bench_map.get(chart_series[0][0]) if chart_series else None
    perf_chart = dict(type="line", pct=True, data=dict(
        labels=[d.strftime("%b %d") for d, _ in chart_series],
        datasets=[dict(label="Portfolio", data=[round((v / chart_series[0][1] - 1) * 100, 2) for _, v in chart_series]),
                  dict(label="S&P 500", data=[round((bench_map.get(d, b0) / b0 - 1) * 100, 2) if b0 else 0 for d, _ in chart_series], borderDash=[4, 4])]))
    return render_template("stocks/dashboard.html", t=t, pos=pos, rets=rets, brets=brets, gainers=movers[::-1][:5], losers=movers[:5],
                           proposals=proposals, buckets=[b[0] for b in buckets], hist=hist, drivers=drivers, affected=affected,
                           conv=conv, earnings=earnings, recent_txns=recent_txns, notes=notes, actions=actions, perf_chart=perf_chart,
                           asof=series[-1][0] if series else date.today())


@bp.route("/refresh", methods=["POST"])
@write_required
def refresh():
    pf.refresh_prices()
    db.session.commit()
    flash("Prices refreshed from the simulated feed.", "success")
    return redirect(request.form.get("next") or url_for(".dashboard"))


# ------------------------------------------------------------------ daily review
@bp.route("/daily-review/")
def daily_review():
    t = pf.totals()
    pos = t["positions"]
    m = month_ago_prices([p.security.id for p in pos])
    rows = []
    for p in pos:
        probs, strengths = pf.problems_for(p, t["long_mv"], m.get(p.security.id))
        rows.append(dict(p=p, probs=probs, strengths=strengths))
    last_day = db.session.query(db.func.max(ReviewSnapshot.day)).filter(ReviewSnapshot.day < date.today()).scalar()
    prev = {s.ticker: set(filter(None, s.problems.split(","))) for s in ReviewSnapshot.query.filter_by(day=last_day)} if last_day else {}
    new, cleared = [], []
    for r in rows:
        now_set = set(r["probs"])
        before = prev.get(r["p"].security.ticker, set())
        if now_set - before:
            new.append((r, sorted(now_set - before)))
        if before - now_set:
            cleared.append((r, sorted(before - now_set)))
    attention = sorted([r for r in rows if len(r["probs"]) >= 2], key=lambda r: (-len(r["probs"]), r["p"].pnl_pct))
    others = [r for r in rows if len(r["probs"]) == 1]
    counts = defaultdict(int)
    for r in rows:
        for pr in r["probs"]:
            counts[pr] += 1
    return render_template("stocks/daily_review.html", t=t, rows=rows, new=new, cleared=cleared, attention=attention,
                           others=others, counts=counts, measures=pf.MEASURES, last_day=last_day)


@bp.route("/daily-review/snapshot", methods=["POST"])
@write_required
def daily_snapshot():
    t = pf.totals()
    m = month_ago_prices([p.security.id for p in t["positions"]])
    ReviewSnapshot.query.filter_by(day=date.today()).delete()
    for p in t["positions"]:
        probs, _ = pf.problems_for(p, t["long_mv"], m.get(p.security.id))
        db.session.add(ReviewSnapshot(day=date.today(), ticker=p.security.ticker, problems=",".join(probs)))
    audit("stocks", "snapshot", "daily_review", None, "Saved today's review snapshot")
    db.session.commit()
    flash("Today's review saved. Tomorrow's 'new problems' will compare against it.", "success")
    return redirect(url_for(".daily_review"))


# ------------------------------------------------------------------ holdings
@bp.route("/holdings/")
def holdings():
    ids, codes = selected_accounts()
    t = pf.totals(ids)
    pos = t["positions"]
    by_acct = pf.positions(ids, by_account=True)
    lots = TaxLot.query.join(Security).filter(TaxLot.shares > 0)
    if ids:
        lots = lots.filter(TaxLot.account_id.in_(ids))
    lots = lots.order_by(Security.ticker, TaxLot.acquired).all()
    acct_rows = []
    for a in t["accounts"]:
        ap = [p for p in by_acct if a in p.accounts]
        mv = sum(p.mv for p in ap)
        cost = sum(p.cost for p in ap)
        acct_rows.append(dict(a=a, n=len(ap), mv=mv, cost=cost, pnl=mv - cost, net=mv + (a.cash or 0) - (a.margin_debt or 0),
                              margin_pct=((a.margin_debt or 0) / mv * 100) if mv else 0))
    series = pf.value_series(pos, 380)
    rets = pf.period_returns(series)
    m = month_ago_prices([p.security.id for p in pos])
    all_accts = BrokerageAccount.query.order_by(BrokerageAccount.id).all()
    perf = []
    for p in pos:
        ma = m.get(p.security.id)
        perf.append(dict(p=p, m1=((p.security.price / ma - 1) * 100) if ma else None))
    return render_template("stocks/holdings.html", t=t, pos=pos, lots=lots, acct_rows=acct_rows, rets=rets, codes=codes,
                           all_accts=all_accts, perf=perf, by_acct=by_acct)


@bp.route("/holdings/month-end/")
def month_end():
    ids, codes = selected_accounts()
    # month-end dates for the last 6 months
    ends = []
    d = date.today().replace(day=1) - timedelta(days=1)
    for _ in range(6):
        ends.append(d)
        d = d.replace(day=1) - timedelta(days=1)
    by_acct = pf.positions(ids, by_account=True)
    sids = list({p.security.id for p in by_acct})
    m = pf.price_matrix(sids, ends[-1] - timedelta(days=10))
    def px_on(sid, day):
        best = None
        for dd, c in sorted(m[sid].items()):
            if dd <= day:
                best = c
        return best or 0
    grid = defaultdict(list)
    for p in by_acct:
        acct = next(iter(p.accounts))
        vals = [p.shares * px_on(p.security.id, e) for e in ends]
        grid[acct].append((p, vals))
    totals = [sum(v[i] for rows in grid.values() for _, v in rows) for i in range(len(ends))]
    return render_template("stocks/month_end.html", grid=grid, ends=ends, totals=totals, codes=codes,
                           all_accts=BrokerageAccount.query.order_by(BrokerageAccount.id).all())


# ------------------------------------------------------------------ activity
TXN_TABS = {"all": None, "trades": ["BUY", "SELL"], "dividends": ["DIV"], "interest": ["INT"], "cash": ["DEP", "WD", "FEE"]}


@bp.route("/trade-log/")
def trade_log():
    tab = request.args.get("tab", "all")
    q = StockTxn.query
    if TXN_TABS.get(tab):
        q = q.filter(StockTxn.kind.in_(TXN_TABS[tab]))
    ids, codes = selected_accounts()
    if ids:
        q = q.filter(StockTxn.account_id.in_(ids))
    term = request.args.get("q", "").strip().upper()
    if term:
        q = q.join(Security, isouter=True).filter(db.or_(Security.ticker.ilike(f"%{term}%"), StockTxn.note.ilike(f"%{term}%")))
    pag = q.order_by(StockTxn.day.desc(), StockTxn.id.desc()).paginate(page=int(request.args.get("page", 1)), per_page=60, error_out=False)
    counts = dict(db.session.query(StockTxn.kind, db.func.count()).group_by(StockTxn.kind).all())
    return render_template("stocks/trade_log.html", pag=pag, tab=tab, tabs=TXN_TABS, counts=counts, codes=codes,
                           all_accts=BrokerageAccount.query.order_by(BrokerageAccount.id).all(),
                           securities=Security.query.filter(Security.stage != "Benchmark").order_by(Security.ticker).all())


@bp.route("/trade-log/new", methods=["POST"])
@write_required
def new_txn():
    f = request.form
    acct = db.session.get(BrokerageAccount, int(f["account_id"])) or abort(400)
    kind = f["kind"]
    try:
        if kind in ("BUY", "SELL"):
            sec = db.session.get(Security, int(f["security_id"])) or abort(400)
            pf.execute_trade(acct, sec, kind, float(f["shares"]), float(f["price"]), fees=float(f.get("fees") or 0),
                             note=f.get("note"), day=date.fromisoformat(f["day"]) if f.get("day") else None)
        else:
            amt = float(f["amount"])
            if kind in ("WD", "FEE") and amt > 0:
                amt = -amt
            sid = int(f["security_id"]) if f.get("security_id") else None
            db.session.add(StockTxn(account=acct, security_id=sid, day=date.fromisoformat(f["day"]) if f.get("day") else date.today(),
                                    kind=kind, amount=amt, note=f.get("note")))
            acct.cash = (acct.cash or 0) + amt
            audit("stocks", "create", "stk_txns", None, f"{kind} {amt:,.2f} in {acct.code}")
        db.session.commit()
        flash(f"{kind} recorded.", "success")
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")
    return redirect(request.form.get("next") or url_for(".trade_log"))


@bp.route("/trade-log/<int:txn_id>/delete", methods=["POST"])
@write_required
def delete_txn(txn_id):
    t = db.session.get(StockTxn, txn_id) or abort(404)
    if t.kind in ("BUY", "SELL"):
        flash("Trades can't be deleted from the log; book an offsetting trade instead.", "error")
    else:
        t.account.cash = (t.account.cash or 0) - (t.amount or 0)
        db.session.delete(t)
        audit("stocks", "delete", "stk_txns", txn_id, f"{t.kind} {t.amount}")
        db.session.commit()
        flash("Entry deleted and cash reversed.", "success")
    return redirect(request.form.get("next") or url_for(".trade_log"))


@bp.route("/trade-log/pnl/")
def pnl():
    year = date.today().year
    sells = StockTxn.query.filter(StockTxn.kind == "SELL").all()
    t = pf.totals()
    realized_ytd = sum(s.realized_pnl or 0 for s in sells if s.day.year == year)
    realized_all = sum(s.realized_pnl or 0 for s in sells)
    divs_ytd = sum(x.amount or 0 for x in StockTxn.query.filter(StockTxn.kind == "DIV").all() if x.day.year == year)
    interest = sum(x.amount or 0 for x in StockTxn.query.filter(StockTxn.kind == "INT").all() if x.day.year == year)
    by_ticker = defaultdict(float)
    for s in sells:
        if s.security:
            by_ticker[s.security.ticker] += s.realized_pnl or 0
    monthly = defaultdict(float)
    for s in sells:
        monthly[s.day.strftime("%Y-%m")] += s.realized_pnl or 0
    months = sorted(monthly)[-12:]
    chart = dict(type="bar", money=True, data=dict(labels=months, datasets=[dict(label="Realized P&L", data=[round(monthly[m]) for m in months],
                                                                                 backgroundColor=["#10b981" if monthly[m] >= 0 else "#ef4444" for m in months])]))
    by_acct = defaultdict(lambda: [0.0, 0.0])
    for p in pf.positions(by_account=True):
        a = next(iter(p.accounts))
        by_acct[a][0] += p.pnl
    for s in sells:
        if s.day.year == year:
            by_acct[s.account][1] += s.realized_pnl or 0
    return render_template("stocks/pnl.html", t=t, realized_ytd=realized_ytd, realized_all=realized_all, divs_ytd=divs_ytd,
                           interest=interest, top=sorted(by_ticker.items(), key=lambda x: -x[1]), chart=chart, by_acct=by_acct,
                           sells=sorted(sells, key=lambda s: s.day, reverse=True)[:40])


@bp.route("/trade-log/pnl/fees/")
def fees():
    txns = StockTxn.query.filter(db.or_(StockTxn.kind == "FEE", StockTxn.fees > 0, db.and_(StockTxn.kind == "INT", StockTxn.amount < 0))).order_by(StockTxn.day.desc()).all()
    by_type = defaultdict(float)
    by_acct = defaultdict(float)
    monthly = defaultdict(float)
    for x in txns:
        amt = abs(x.amount) if x.kind in ("FEE", "INT") else (x.fees or 0)
        label = x.note if x.kind == "FEE" else ("Margin interest" if x.kind == "INT" else "Commissions")
        by_type[label] += amt
        by_acct[x.account.name] += amt
        monthly[x.day.strftime("%Y-%m")] += amt
    months = sorted(monthly)[-12:]
    chart = dict(type="bar", money=True, data=dict(labels=months, datasets=[dict(label="Fees & interest", data=[round(monthly[m]) for m in months], backgroundColor="#f59e0b")]))
    return render_template("stocks/fees.html", txns=txns[:120], by_type=sorted(by_type.items(), key=lambda x: -x[1]),
                           by_acct=sorted(by_acct.items(), key=lambda x: -x[1]), chart=chart, total=sum(by_type.values()))


# ------------------------------------------------------------------ options / dividends
@bp.route("/options/")
def options():
    opts = OptionPosition.query.order_by(OptionPosition.status.desc(), OptionPosition.expiry).all()
    open_ = [o for o in opts if o.status == "open"]
    premium = sum(-o.contracts * 100 * o.premium for o in open_)
    liability = sum(-o.contracts * 100 * o.mark for o in open_)
    notional = sum(-o.contracts * 100 * o.strike for o in open_ if o.right == "PUT")
    return render_template("stocks/options.html", opts=opts, open_=open_, premium=premium, liability=liability, notional=notional)


@bp.route("/options/<int:oid>/close", methods=["POST"])
@write_required
def close_option(oid):
    o = db.session.get(OptionPosition, oid) or abort(404)
    pnl = -o.contracts * 100 * (o.premium - o.mark)
    o.status = "closed"
    db.session.add(StockTxn(account=o.account, security=o.security, day=date.today(), kind="SELL" if o.contracts > 0 else "BUY",
                            shares=abs(o.contracts) * 100, price=o.mark, amount=o.contracts * 100 * o.mark, realized_pnl=pnl,
                            note=f"Close {o.security.ticker} {o.strike:g}{o.right[0]} {o.expiry:%m/%d}"))
    o.account.cash = (o.account.cash or 0) + o.contracts * 100 * o.mark
    audit("stocks", "close", "stk_options", oid, f"Closed {o.security.ticker} option, P&L {pnl:,.0f}")
    db.session.commit()
    flash(f"Closed {o.security.ticker} {o.strike:g} {o.right.lower()} · realized {pnl:+,.0f}.", "success")
    return redirect(url_for(".options"))


@bp.route("/dividends/")
def dividends():
    divs = StockTxn.query.filter_by(kind="DIV").order_by(StockTxn.day.desc()).all()
    pos = pf.positions()
    proj = sorted([(p, p.mv * (p.security.div_yield or 0) / 100) for p in pos if (p.security.div_yield or 0) > 0], key=lambda x: -x[1])
    monthly = defaultdict(float)
    for d in divs:
        monthly[d.day.strftime("%Y-%m")] += d.amount or 0
    months = sorted(monthly)[-12:]
    chart = dict(type="bar", money=True, data=dict(labels=months, datasets=[dict(label="Dividends", data=[round(monthly[m]) for m in months], backgroundColor="#10b981")]))
    ttm = sum(d.amount for d in divs if d.day >= date.today() - timedelta(days=365))
    upcoming = CorporateAction.query.filter(CorporateAction.kind.ilike("%dividend%"), CorporateAction.ex_date >= date.today()).order_by(CorporateAction.ex_date).all()
    return render_template("stocks/dividends.html", divs=divs[:80], proj=proj, chart=chart, ttm=ttm,
                           fwd=sum(x[1] for x in proj), upcoming=upcoming, long_mv=sum(p.mv for p in pos))


# ------------------------------------------------------------------ exposure
@bp.route("/exposure/")
def exposure():
    t = pf.totals()
    pos = t["positions"]
    def group(attr):
        g = defaultdict(float)
        for p in pos:
            g[getattr(p.security, attr) or "Other"] += p.mv
        return sorted(g.items(), key=lambda x: -x[1])
    sectors, themes = group("sector"), group("theme")
    beta = sum(p.mv * (p.security.beta or 1) for p in pos) / t["long_mv"] if t["long_mv"] else 0
    top10 = sum(p.mv for p in pos[:10]) / t["long_mv"] * 100 if t["long_mv"] else 0
    drivers = Driver.query.order_by(Driver.kind, Driver.code).all()
    expo = defaultdict(list)
    for e in DriverExposure.query.all():
        expo[e.driver_id].append(e)
    mv_by_sid = {p.security.id: p.mv for p in pos}
    driver_rows = []
    for d in drivers:
        es = expo[d.id]
        dollar_beta = sum(mv_by_sid.get(e.security_id, 0) * e.beta for e in es)
        driver_rows.append(dict(d=d, n=len(es), dollar_beta=dollar_beta, impact=dollar_beta * (d.change_1d or 0) / 100, es=sorted(es, key=lambda e: -abs(e.beta))))
    sector_chart = dict(type="doughnut", money=True, data=dict(labels=[s for s, _ in sectors], datasets=[dict(data=[round(v) for _, v in sectors])]))
    theme_chart = dict(type="bar", money=True, options=dict(indexAxis="y"), data=dict(labels=[s for s, _ in themes], datasets=[dict(label="Market value", data=[round(v) for _, v in themes])]))
    return render_template("stocks/exposure.html", t=t, sectors=sectors, themes=themes, beta=beta, top10=top10, driver_rows=driver_rows,
                           sector_chart=sector_chart, theme_chart=theme_chart, pos=pos)


@bp.route("/exposure/market/")
def market():
    idx = MarketIndex.query.order_by(MarketIndex.sort).all()
    pos = pf.positions()
    sec_moves = defaultdict(lambda: [0.0, 0.0])
    for p in pos:
        sec_moves[p.security.sector][0] += p.day_pnl
        sec_moves[p.security.sector][1] += p.mv
    bench = pf.bench_series(380)
    chart = dict(type="line", data=dict(labels=[d.strftime("%b %d") for d, _ in bench[-250:]], datasets=[dict(label="S&P 500", data=[v for _, v in bench[-250:]])]))
    movers = sorted(Security.query.filter(Security.stage != "Benchmark").all(), key=lambda s: s.change_pct)
    return render_template("stocks/market.html", idx=idx, sec_moves=sorted(sec_moves.items(), key=lambda x: x[1][0]), chart=chart,
                           up=movers[::-1][:10], down=movers[:10], drivers=Driver.query.order_by(Driver.code).all())


@bp.route("/categories/")
def categories():
    t = pf.totals()
    cats = defaultdict(list)
    for p in t["positions"]:
        cats[p.security.category or "Public Equity"].append(p)
    rows = sorted(cats.items(), key=lambda x: -sum(p.mv for p in x[1]))
    chart = dict(type="doughnut", money=True, data=dict(labels=[c for c, _ in rows] + ["Cash (net of margin)"],
                                                        datasets=[dict(data=[round(sum(p.mv for p in ps)) for _, ps in rows] + [max(0, round(t["cash_net"]))])]))
    return render_template("stocks/categories.html", t=t, rows=rows, chart=chart, cats=CATS)


@bp.route("/categories/set", methods=["POST"])
@write_required
def set_category():
    s = db.session.get(Security, int(request.form["security_id"])) or abort(404)
    s.category = request.form["category"]
    audit("stocks", "update", "stk_securities", s.id, f"{s.ticker} category → {s.category}")
    db.session.commit()
    flash(f"{s.ticker} moved to {s.category}.", "success")
    return redirect(url_for(".categories"))


# ------------------------------------------------------------------ research
REVIEW_COLS = ["Queued", "In Review", "Done"]


@bp.route("/review/")
def review():
    secs = Security.query.filter(Security.stage.in_(["Active", "Watch"])).order_by(Security.next_review).all()
    cols = {c: [s for s in secs if s.review_status == c] for c in REVIEW_COLS}
    backlog = [s for s in secs if s.review_status in (None, "None")]
    return render_template("stocks/review.html", cols=cols, backlog=backlog, users=User.query.filter(User.role != "investor").all())


@bp.route("/review/<int:sid>/move", methods=["POST"])
@write_required
def review_move(sid):
    s = db.session.get(Security, sid) or abort(404)
    st = request.form.get("status")
    if st not in REVIEW_COLS + ["None"]:
        abort(400)
    s.review_status = st
    if request.form.get("conviction"):
        s.conviction = int(request.form["conviction"])
    s.reviewer = s.reviewer or current_user.first_name
    if st == "Done":
        s.next_review = date.today() + timedelta(days=90)
    audit("stocks", "review", "stk_securities", s.id, f"{s.ticker} review → {st}")
    db.session.commit()
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Refresh": "true"}
    flash(f"{s.ticker} moved to {st}.", "success")
    return redirect(url_for(".review"))


@bp.route("/themes/")
def themes():
    pos = pf.positions()
    m = month_ago_prices([p.security.id for p in pos])
    th = defaultdict(list)
    for p in pos:
        th[p.security.theme or "Other"].append(p)
    rows = []
    for name, ps in th.items():
        mv = sum(p.mv for p in ps)
        cost = sum(p.cost for p in ps)
        m1 = sum(p.shares * m.get(p.security.id, p.security.price) for p in ps)
        rows.append(dict(name=name, ps=sorted(ps, key=lambda p: -p.mv), mv=mv, pnl=mv - cost, pnl_pct=(mv / cost - 1) * 100 if cost else 0,
                         m1=(mv / m1 - 1) * 100 if m1 else 0, day=sum(p.day_pnl for p in ps)))
    rows.sort(key=lambda r: -r["mv"])
    total = sum(r["mv"] for r in rows)
    return render_template("stocks/themes.html", rows=rows, total=total)


@bp.route("/watchlist/")
def watchlist():
    items = WatchItem.query.join(Security).order_by(Security.ticker).all()
    held = {p.security.id for p in pf.positions()}
    return render_template("stocks/watchlist.html", items=items, held=held,
                           securities=Security.query.filter(Security.stage != "Benchmark").order_by(Security.ticker).all())


@bp.route("/actions/")
def actions():
    pending = TradeProposal.query.filter_by(status="pending").order_by(TradeProposal.created_at).all()
    decided = TradeProposal.query.filter(TradeProposal.status != "pending").order_by(TradeProposal.decided_at.desc()).limit(30).all()
    t = pf.totals()
    impact = defaultdict(float)
    for p in pending:
        px = p.limit_price or p.security.price
        impact[p.account.code] += (-1 if p.action in ("BUY", "ADD") else 1) * p.shares * px
    return render_template("stocks/actions.html", pending=pending, decided=decided, t=t, impact=impact,
                           accts=BrokerageAccount.query.order_by(BrokerageAccount.id).all(),
                           securities=Security.query.filter(Security.stage != "Benchmark").order_by(Security.ticker).all(),
                           ca=CorporateAction.query.filter_by(status="Pending").order_by(CorporateAction.ex_date).all())


@bp.route("/actions/propose", methods=["POST"])
@write_required
def propose():
    f = request.form
    try:
        p = TradeProposal(account_id=int(f["account_id"]), security_id=int(f["security_id"]), action=f["action"],
                          shares=float(f["shares"]), limit_price=float(f["limit_price"]) if f.get("limit_price") else None,
                          reason=f.get("reason"), proposed_by_id=current_user.id)
        if p.shares <= 0:
            raise ValueError
    except (ValueError, KeyError):
        flash("Fill in account, security, action and a positive share count.", "error")
        return redirect(url_for(".actions"))
    db.session.add(p)
    db.session.flush()
    audit("stocks", "create", "stk_proposals", p.id, f"Proposed {p.action} {p.shares:,.0f}")
    db.session.commit()
    flash("Trade proposal submitted for approval.", "success")
    return redirect(url_for(".actions"))


@bp.route("/actions/<int:pid>/<decision>", methods=["POST"])
@write_required
def decide(pid, decision):
    p = db.session.get(TradeProposal, pid) or abort(404)
    if p.status != "pending" or decision not in ("approve", "reject"):
        abort(400)
    if decision == "approve":
        if not current_user.is_admin:
            abort(403)
        price = p.limit_price or p.security.price
        try:
            pf.execute_trade(p.account, p.security, p.action, p.shares, price, note=f"Proposal #{p.id}: {(p.reason or '')[:120]}")
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")
            return redirect(url_for(".actions"))
        p.status = "approved"
    else:
        p.status = "rejected"
    p.decided_by_id = current_user.id
    p.decided_at = datetime.utcnow()
    audit("stocks", decision, "stk_proposals", p.id, f"{decision.title()}d {p.action} {p.shares:,.0f} {p.security.ticker}")
    db.session.commit()
    flash(f"{p.action} {p.shares:,.0f} {p.security.ticker} {p.status}." + (" Trade booked." if p.status == "approved" else ""), "success")
    return redirect(request.form.get("next") or url_for(".actions"))


@bp.route("/notes/")
def notes():
    q = StockNote.query
    if request.args.get("t"):
        q = q.join(Security).filter(Security.ticker == request.args["t"].upper())
    items = q.order_by(StockNote.pinned.desc(), StockNote.created_at.desc()).all()
    return render_template("stocks/notes.html", items=items, securities=Security.query.order_by(Security.ticker).all())


@bp.route("/notes/quick", methods=["POST"])
@write_required
def quick_note():
    title = request.form.get("title", "").strip()
    if not title:
        flash("A note needs a title.", "error")
        return redirect(url_for(".notes"))
    n = StockNote(title=title, body=request.form.get("body"), author_id=current_user.id,
                  security_id=int(request.form["security_id"]) if request.form.get("security_id") else None)
    db.session.add(n)
    db.session.flush()
    audit("stocks", "create", "stk_notes", n.id, title)
    db.session.commit()
    flash("Note saved.", "success")
    return redirect(url_for(".notes"))


def _series_for(tickers, days):
    secs = Security.query.filter(Security.ticker.in_(tickers)).all()
    since = date.today() - timedelta(days=days)
    m = pf.price_matrix([s.id for s in secs], since)
    return secs, m


@bp.route("/comparison/")
def comparison():
    tickers = [t.strip().upper() for t in request.args.get("t", "NVDA,MSFT,AAPL,SPX").split(",") if t.strip()][:8]
    days = int(request.args.get("days", 365))
    secs, m = _series_for(tickers, days)
    labels = sorted({d for s in m.values() for d in s})
    ds = []
    for s in secs:
        pts = m[s.id]
        base = pts[min(pts)] if pts else 1
        ds.append(dict(label=s.ticker, data=[round((pts.get(d, None) or base) / base * 100 - 100, 2) for d in labels]))
    chart = dict(type="line", pct=True, data=dict(labels=[d.strftime("%b %d") for d in labels], datasets=ds))
    return render_template("stocks/comparison.html", secs=secs, chart=chart, tickers=tickers, days=days,
                           all_secs=Security.query.order_by(Security.ticker).all())


@bp.route("/charts/")
def charts():
    tk = request.args.get("t", "NVDA").upper()
    days = int(request.args.get("days", 180))
    s = Security.query.filter_by(ticker=tk).first() or abort(404)
    bars = PriceBar.query.filter(PriceBar.security_id == s.id, PriceBar.day >= date.today() - timedelta(days=days + 60)).order_by(PriceBar.day).all()
    closes = [b.close for b in bars]
    ma = [round(sum(closes[max(0, i - 49):i + 1]) / len(closes[max(0, i - 49):i + 1]), 2) for i in range(len(closes))]
    cut = max(0, len(bars) - len([b for b in bars if b.day >= date.today() - timedelta(days=days)]))
    chart = dict(type="line", data=dict(labels=[b.day.strftime("%b %d") for b in bars[cut:]],
                                        datasets=[dict(label=tk, data=closes[cut:]), dict(label="50-day avg", data=ma[cut:], borderDash=[4, 4])]))
    lots = TaxLot.query.filter_by(security_id=s.id).filter(TaxLot.shares > 0).all()
    return render_template("stocks/charts.html", s=s, chart=chart, days=days, lots=lots,
                           notes=StockNote.query.filter_by(security_id=s.id).all(),
                           all_secs=Security.query.order_by(Security.ticker).all())


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    keys = [("concentration_limit", "Single-name limit (% of long value)", "6"), ("margin_target", "Margin target (% of long value)", "30"),
            ("daily_review_time", "Daily review email time (ET)", "07:30"), ("daily_review_to", "Daily review recipients", "tirumala@bhuram-fo.example, marcus@bhuram-fo.example"),
            ("approval_threshold", "Trades above this $ need Super Admin approval", "250000")]
    if request.method == "POST":
        if not current_user.is_admin:
            abort(403)
        for k, label, _ in keys:
            s = Setting.query.filter_by(scope="stocks", key=k).first() or Setting(scope="stocks", key=k, label=label)
            s.value = request.form.get(k, "")
            db.session.add(s)
        audit("stocks", "update", "settings", None, "Stocks settings saved")
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for(".settings"))
    vals = {k: (Setting.query.filter_by(scope="stocks", key=k).first().value if Setting.query.filter_by(scope="stocks", key=k).first() else d) for k, _, d in keys}
    return render_template("stocks/settings.html", keys=keys, vals=vals, accts=BrokerageAccount.query.order_by(BrokerageAccount.id).all())

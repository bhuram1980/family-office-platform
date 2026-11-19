import math
from datetime import date, timedelta, datetime

from ..extensions import db
from ..models import (BrokerageAccount, Security, PriceBar, TaxLot, StockTxn, TradeProposal, OptionPosition,
                       WatchItem, StockNote, Driver, DriverExposure, MarketIndex, CorporateAction, ReviewSnapshot)
from ..services.portfolio import positions, problems_for

# ticker, name, sector, theme, approx price, beta, pe, div yield, rev growth
SECS = """NVDA|NVIDIA|Technology|AI Compute|142|1.7|48|0.03|62
MSFT|Microsoft|Technology|Cloud Platforms|468|1.0|35|0.7|15
AAPL|Apple|Technology|Consumer Platforms|231|1.1|33|0.45|6
AMZN|Amazon.com|Consumer Discretionary|Cloud Platforms|214|1.2|42|0|11
GOOGL|Alphabet A|Communication|AI Compute|187|1.1|24|0.45|14
META|Meta Platforms|Communication|Consumer Platforms|612|1.3|27|0.33|21
AVGO|Broadcom|Technology|AI Compute|226|1.4|38|1.0|44
TSM|Taiwan Semiconductor|Technology|AI Compute|201|1.3|27|1.2|38
AMD|Advanced Micro Devices|Technology|AI Compute|158|1.8|52|0|24
ANET|Arista Networks|Technology|AI Compute|109|1.5|44|0|27
MU|Micron Technology|Technology|AI Compute|131|1.6|19|0.4|58
CRWD|CrowdStrike|Technology|Cybersecurity|402|1.4|88|0|29
PANW|Palo Alto Networks|Technology|Cybersecurity|196|1.2|51|0|15
ZS|Zscaler|Technology|Cybersecurity|238|1.3|70|0|23
NET|Cloudflare|Technology|Cybersecurity|121|1.5|0|0|28
PLTR|Palantir|Technology|AI Software|74|2.0|160|0|33
SNOW|Snowflake|Technology|AI Software|171|1.6|0|0|26
NOW|ServiceNow|Technology|AI Software|1012|1.1|62|0|22
CRM|Salesforce|Technology|AI Software|318|1.1|31|0.5|9
ADBE|Adobe|Technology|AI Software|428|1.1|26|0|10
ORCL|Oracle|Technology|Cloud Platforms|176|1.0|33|0.9|9
INTU|Intuit|Technology|AI Software|655|1.2|39|0.6|13
SHOP|Shopify|Technology|Consumer Platforms|108|1.9|80|0|24
UBER|Uber Technologies|Industrials|Consumer Platforms|79|1.3|36|0|18
NFLX|Netflix|Communication|Consumer Platforms|884|1.2|44|0|16
SPOT|Spotify|Communication|Consumer Platforms|488|1.3|90|0|19
COST|Costco|Consumer Staples|Quality Compounders|932|0.8|52|0.5|7
WMT|Walmart|Consumer Staples|Quality Compounders|94|0.6|37|0.9|5
HD|Home Depot|Consumer Discretionary|Housing Recovery|402|1.0|27|2.2|4
LOW|Lowe's|Consumer Discretionary|Housing Recovery|261|1.1|22|1.8|2
NKE|Nike|Consumer Discretionary|Turnarounds|73|1.0|29|2.0|-4
SBUX|Starbucks|Consumer Discretionary|Turnarounds|98|0.9|31|2.4|-1
MCD|McDonald's|Consumer Discretionary|Quality Compounders|296|0.7|25|2.3|3
JPM|JPMorgan Chase|Financials|Financial Infrastructure|244|1.1|13|2.0|9
GS|Goldman Sachs|Financials|Financial Infrastructure|588|1.3|16|2.0|12
MS|Morgan Stanley|Financials|Financial Infrastructure|131|1.3|18|2.8|10
V|Visa|Financials|Financial Infrastructure|314|0.9|31|0.7|10
MA|Mastercard|Financials|Financial Infrastructure|527|1.0|38|0.5|12
BX|Blackstone|Financials|Alternative Managers|172|1.5|52|2.1|8
KKR|KKR & Co|Financials|Alternative Managers|149|1.6|31|0.5|14
APO|Apollo Global|Financials|Alternative Managers|161|1.5|19|1.2|11
SCHW|Charles Schwab|Financials|Financial Infrastructure|79|1.0|29|1.3|7
BRK.B|Berkshire Hathaway B|Financials|Quality Compounders|471|0.8|9|0|5
LLY|Eli Lilly|Health Care|GLP-1 & Obesity|812|0.5|86|0.7|36
NVO|Novo Nordisk|Health Care|GLP-1 & Obesity|86|0.4|27|1.6|21
UNH|UnitedHealth|Health Care|Healthcare Services|361|0.6|23|2.3|7
ISRG|Intuitive Surgical|Health Care|Medical Technology|528|1.0|81|0|17
VRTX|Vertex Pharmaceuticals|Health Care|Biotech Leaders|463|0.5|29|0|9
TMO|Thermo Fisher|Health Care|Medical Technology|521|0.8|31|0.3|2
ABBV|AbbVie|Health Care|Biotech Leaders|186|0.6|17|3.4|5
DHR|Danaher|Health Care|Medical Technology|233|0.9|38|0.5|-2
XOM|Exxon Mobil|Energy|Energy Transition|113|0.9|14|3.4|-3
CVX|Chevron|Energy|Energy Transition|152|0.9|15|4.3|-2
VST|Vistra|Utilities|Power Demand|141|1.4|24|0.6|18
CEG|Constellation Energy|Utilities|Power Demand|257|1.2|30|0.6|10
NEE|NextEra Energy|Utilities|Energy Transition|74|0.6|21|2.8|6
GEV|GE Vernova|Industrials|Power Demand|338|1.4|58|0.1|9
ETN|Eaton|Industrials|Power Demand|342|1.2|35|1.1|8
CAT|Caterpillar|Industrials|Infrastructure|381|1.1|18|1.5|-1
DE|Deere|Industrials|Infrastructure|418|0.9|17|1.5|-8
URI|United Rentals|Industrials|Infrastructure|778|1.4|21|0.9|6
GE|GE Aerospace|Industrials|Aerospace|182|1.2|34|0.6|9
RTX|RTX Corp|Industrials|Aerospace|121|0.8|33|2.1|8
LMT|Lockheed Martin|Industrials|Aerospace|512|0.5|19|2.6|4
HON|Honeywell|Industrials|Infrastructure|219|1.0|24|2.0|5
LIN|Linde|Materials|Quality Compounders|448|0.9|33|1.3|2
FCX|Freeport-McMoRan|Materials|Energy Transition|41|1.6|31|1.4|9
NUE|Nucor|Materials|Infrastructure|139|1.3|16|1.6|-9
AMT|American Tower|Real Estate|Digital Infrastructure|198|0.8|40|3.3|1
EQIX|Equinix|Real Estate|Digital Infrastructure|902|0.7|89|1.9|7
PLD|Prologis|Real Estate|Digital Infrastructure|112|1.0|33|3.4|5
TSLA|Tesla|Consumer Discretionary|Autonomy|271|2.1|95|0|2
ASML|ASML Holding|Technology|AI Compute|705|1.3|35|0.9|15
ARM|Arm Holdings|Technology|AI Compute|141|2.0|170|0|26
SMCI|Super Micro Computer|Technology|AI Compute|33|2.4|17|0|52
VRT|Vertiv|Industrials|Power Demand|118|1.7|47|0.1|19
DDOG|Datadog|Technology|AI Software|129|1.4|0|0|25
MELI|MercadoLibre|Consumer Discretionary|Consumer Platforms|1977|1.4|58|0|36
SE|Sea Ltd|Consumer Discretionary|Consumer Platforms|108|1.5|0|0|29
BABA|Alibaba|Consumer Discretionary|Turnarounds|91|0.6|14|1.1|5
SGOV|iShares 0-3M Treasury|Cash|Cash Management|100.4|0.0|0|4.6|0
GLD|SPDR Gold Shares|Commodities|Real Assets|244|0.1|0|0|0
IBIT|iShares Bitcoin Trust|Alternatives|Digital Assets|53|1.9|0|0|0
VNQ|Vanguard Real Estate ETF|Real Estate|Real Assets|92|1.0|0|3.9|0"""

WATCH_ONLY = """APP|AppLovin|Technology|AI Software|312|2.2|72|0|41
HOOD|Robinhood Markets|Financials|Financial Infrastructure|38|2.3|55|0|36
DUOL|Duolingo|Communication|Consumer Platforms|318|1.6|160|0|41
AXON|Axon Enterprise|Industrials|Autonomy|598|1.3|140|0|33
ELF|e.l.f. Beauty|Consumer Staples|Turnarounds|112|1.6|45|0|26
CMG|Chipotle|Consumer Discretionary|Quality Compounders|58|1.1|52|0|14
TTD|The Trade Desk|Technology|AI Software|119|1.6|190|0|26
RKLB|Rocket Lab|Industrials|Aerospace|23|2.1|0|0|52"""

ACCOUNTS = [("Alladin Family Trust", "BFT", "Alladin Family Trust", "Charles Schwab", "Taxable"),
            ("Alladin Growth Trust", "BGT", "Alladin Growth Trust", "Fidelity", "Taxable"),
            ("Alladin Holdings LLC", "BHL", "Alladin Holdings LLC", "Interactive Brokers", "Taxable · Margin"),
            ("Alladin Foundation", "BFN", "Alladin Foundation", "Morgan Stanley", "Tax-exempt"),
            ("Roth IRA — Tirumala", "RIRA", "Tirumala", "Fidelity", "Retirement"),
            ("Rollover IRA — Tirumala", "TIRA", "Tirumala", "Charles Schwab", "Retirement")]

CATEGORY = {"Cash": "Money Market", "Commodities": "Alternative Inv.", "Alternatives": "Alternative Inv."}


def gbm_history(rnd, end_price, days, vol, drift):
    """Generate a price path ending at end_price, walking backwards."""
    prices = [end_price]
    p = end_price
    for _ in range(days - 1):
        p = p / math.exp(rnd.gauss(drift, vol))
        prices.append(max(p, 0.5))
    return list(reversed(prices))


def parse(block):
    out = []
    for line in block.strip().splitlines():
        t, n, sec, th, px, beta, pe, dy, rg = line.split("|")
        out.append(dict(ticker=t, name=n, sector=sec, theme=th, price=float(px), beta=float(beta), pe=float(pe) or None,
                        div_yield=float(dy), revenue_growth=float(rg)))
    return out


def seed(ctx):
    rnd = ctx["rnd"]
    users = ctx["users"]
    today = date.today()
    accts = []
    for name, code, ent, cust, kind in ACCOUNTS:
        a = BrokerageAccount(name=name, code=code, entity=ent, custodian=cust, kind=kind,
                             acct_no=f"****{rnd.randint(1000, 9999)}", cash=round(rnd.uniform(150_000, 2_400_000), 2),
                             margin_debt=0, margin_limit_pct=35.0)
        accts.append(a)
        db.session.add(a)
    accts[2].margin_debt = 6_850_000
    accts[2].cash = 0
    accts[0].margin_debt = 1_240_000

    secs = []
    held = parse(SECS)
    watch = parse(WATCH_ONLY)
    for d in held + watch:
        s = Security(**d)
        s.category = CATEGORY.get(d["sector"], "Public Equity")
        s.industry = d["theme"]
        s.mkt_cap_b = round(d["price"] * rnd.uniform(0.5, 18), 1)
        s.eps = round(d["price"] / d["pe"], 2) if d["pe"] else None
        s.gross_margin = round(rnd.uniform(18, 82), 1)
        s.next_earnings = today + timedelta(days=rnd.randint(-20, 75))
        s.conviction = rnd.choice([1, 2, 3, 3, 3, 4, 4, 5])
        s.stage = "Watch" if d in watch else "Active"
        s.review_status = rnd.choice(["None", "None", "None", "Queued", "In Review", "Done"])
        s.reviewer = rnd.choice(["Marcus", "Sofia", "Tirumala"]) if s.review_status != "None" else None
        s.next_review = today + timedelta(days=rnd.randint(3, 80))
        secs.append(s)
        db.session.add(s)
    spx = Security(ticker="SPX", name="S&P 500 Index", sector="Index", theme="Benchmark", category="Benchmark",
                   price=6104.0, beta=1.0, stage="Benchmark")
    db.session.add(spx)
    db.session.flush()

    # price history (400 calendar days, weekdays only)
    days = [today - timedelta(days=i) for i in range(400)]
    days = sorted(d for d in days if d.weekday() < 5)
    rows = []
    for s in secs + [spx]:
        vol = 0.007 if s is spx else 0.016 * (s.beta or 1) + 0.004
        drift = 0.0005 if s is spx else rnd.uniform(-0.0012, 0.0024)
        path = gbm_history(rnd, s.price, len(days), vol, drift)
        for d, c in zip(days, path):
            rows.append(dict(security_id=s.id, day=d, close=round(c, 2)))
        s.prev_close = round(path[-2], 2)
        s.high_52w = round(max(path[-260:]), 2)
        s.low_52w = round(min(path[-260:]), 2)
    db.session.bulk_insert_mappings(PriceBar, rows)
    hist = {}
    for r in rows:
        hist.setdefault(r["security_id"], []).append(r["close"])

    # lots: each held security in 1-3 accounts
    for s in [x for x in secs if x.stage == "Active"]:
        path = hist[s.id]
        for a in rnd.sample(accts, rnd.choice([1, 1, 2, 2, 3])):
            for _ in range(rnd.choice([1, 1, 2, 3])):
                idx = rnd.randint(0, len(path) - 30)
                cost = path[idx] * rnd.uniform(.55, 1.25)
                target = rnd.uniform(60_000, 900_000) * (3 if s.ticker in ("NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "SGOV") else 1)
                sh = max(5, round(target / s.price / 5) * 5)
                acq = days[idx] - timedelta(days=rnd.randint(0, 900))
                db.session.add(TaxLot(account=a, security=s, shares=sh, cost_per_share=round(cost, 2), acquired=acq))
                db.session.add(StockTxn(account=a, security=s, day=acq, kind="BUY", shares=sh, price=round(cost, 2),
                                        amount=-round(sh * cost, 2), fees=round(rnd.choice([0, 0, 1.5, 4.95]), 2)))
    db.session.flush()

    # historical activity
    for i in range(260):
        d = today - timedelta(days=rnd.randint(0, 364))
        a = rnd.choice(accts)
        kind = rnd.choices(["SELL", "DIV", "INT", "DEP", "WD", "FEE", "BUY"], [14, 30, 12, 6, 4, 6, 10])[0]
        s = rnd.choice(secs[:len(held)])
        if kind in ("BUY", "SELL"):
            sh = rnd.randint(1, 40) * 10
            px = round(s.price * rnd.uniform(.75, 1.1), 2)
            db.session.add(StockTxn(account=a, security=s, day=d, kind=kind, shares=sh, price=px,
                                    amount=(-1 if kind == "BUY" else 1) * round(sh * px, 2), fees=round(rnd.choice([0, 1.5, 4.95]), 2),
                                    realized_pnl=round(sh * px * rnd.uniform(-.25, .6), 2) if kind == "SELL" else None))
        elif kind == "DIV":
            ds = [x for x in secs if x.div_yield > 0.4]
            s = rnd.choice(ds)
            db.session.add(StockTxn(account=a, security=s, day=d, kind="DIV", amount=round(rnd.uniform(400, 18000), 2), note="Qualified dividend"))
        elif kind == "INT":
            amt = round(rnd.uniform(800, 9000), 2) * (-1 if a.margin_debt else 1)
            db.session.add(StockTxn(account=a, day=d, kind="INT", amount=amt, note="Margin interest" if amt < 0 else "Sweep interest"))
        elif kind in ("DEP", "WD"):
            db.session.add(StockTxn(account=a, day=d, kind=kind, amount=round(rnd.uniform(50, 750)) * 1000 * (1 if kind == "DEP" else -1),
                                    note="Wire from operating account" if kind == "DEP" else "Wire to Alladin Holdings operating"))
        else:
            db.session.add(StockTxn(account=a, day=d, kind="FEE", amount=-round(rnd.uniform(150, 6200), 2),
                                    note=rnd.choice(["Advisory fee", "ADR custody fee", "Wire fee", "Foreign tax withheld"])))

    by_t = {s.ticker: s for s in secs}
    for t, a, act, sh, reason, by, st in [
        ("AVGO", 2, "TRIM", 400, "Position is above the 6% single-name limit after the run; trim back to target.", "marcus", "pending"),
        ("CEG", 1, "BUY", 350, "Starter position in power demand; size to 1% of the Growth Trust.", "marcus", "pending"),
        ("NKE", 0, "SELL", 1200, "Thesis broken: two guide-downs and inventory still rising. Exit and harvest the loss.", "sofia", "pending"),
        ("LLY", 4, "ADD", 60, "Add on the pullback; Roth is the right home for the long-duration winner.", "marcus", "pending"),
        ("SMCI", 2, "SELL", 800, "Accounting overhang; cut the position.", "marcus", "approved"),
        ("BABA", 1, "BUY", 1500, "Deep value; revisit after the next print.", "sofia", "rejected"),
    ]:
        acct = accts[a]
        if act in ("TRIM", "SELL"):
            db.session.flush()
            holders = {}
            for l in TaxLot.query.filter_by(security_id=by_t[t].id).all():
                holders[l.account] = holders.get(l.account, 0) + l.shares
            if holders:
                acct, held_sh = max(holders.items(), key=lambda kv: kv[1])
                sh = max(5, min(sh, int(held_sh * .4) // 5 * 5))
        p = TradeProposal(account=acct, security=by_t[t], action=act, shares=sh, limit_price=round(by_t[t].price * (0.99 if act in ("BUY", "ADD") else 1.01), 2),
                          reason=reason, status=st, proposed_by=users[by])
        if st != "pending":
            p.decided_by = users["tirumala"]
            p.decided_at = datetime.utcnow() - timedelta(days=rnd.randint(3, 20))
        db.session.add(p)

    for t, right, k_mult, exp_days, ctr in [("AAPL", "PUT", .9, 23, -10), ("MSFT", "PUT", .92, 30, -6), ("NVDA", "PUT", .85, 16, -20),
                                            ("META", "CALL", 1.12, 37, -5), ("JPM", "PUT", .93, 9, -15), ("COST", "CALL", 1.08, 44, -3),
                                            ("AMZN", "PUT", .9, 58, -12), ("XOM", "CALL", 1.06, 23, -20), ("TSLA", "PUT", .8, 16, -8),
                                            ("V", "PUT", .94, 72, -10), ("GOOGL", "CALL", 1.1, 30, -12)]:
        s = by_t[t]
        prem = round(s.price * rnd.uniform(.012, .035), 2)
        db.session.add(OptionPosition(account=rnd.choice(accts[:3]), security=s, right=right, strike=round(s.price * k_mult / 5) * 5,
                                      expiry=today + timedelta(days=exp_days), contracts=ctr, premium=prem, mark=round(prem * rnd.uniform(.15, 1.4), 2)))

    for s in [x for x in secs if x.stage == "Watch"] + rnd.sample(secs[:len(held)], 6):
        db.session.add(WatchItem(security=s, target_price=round(s.price * rnd.uniform(.78, .95), 2),
                                 note=rnd.choice(["Buy below target; wait for estimate reset", "Add on a 15% pullback",
                                                  "Watch margins next quarter", "Valuation stretched — patience", "Possible replacement for a laggard"])))
    for t, title, body in [
        ("NVDA", "Data-centre capex check", "Hyperscaler capex guides imply another year of growth; the risk is digestion in the second half. Keep the core, trim above 7% weight."),
        ("LLY", "Supply catching up", "Manufacturing capacity doubles by year-end. Volume, not price, drives the next leg."),
        ("NKE", "Turnaround is slower than hoped", "Wholesale reset is still in progress. Thesis on watch until inventory normalises."),
        (None, "Margin policy", "Keep Holdings LLC margin under 30% of long value; hard limit 35%. Review weekly."),
        ("CEG", "Nuclear PPAs", "Long-dated contracts with hyperscalers re-rate the fleet; position sizing is the question, not direction."),
        (None, "Tax-loss harvest list", "Candidates: NKE, SBUX, DHR, NUE. Mind wash-sale windows across trusts."),
        ("VST", "Power demand basket", "Pair with GEV and ETN; equal-weight the basket at 4% combined."),
        ("CRWD", "Post-outage review", "Retention held. Net new ARR re-accelerating. Conviction back to 4."),
        ("BRK.B", "Cash pile", "Record cash gives optionality; fine as a ballast position."),
        (None, "Quarterly rebalance checklist", "1) Confirm cash needs with Family Office. 2) Check concentration. 3) Review option book rolls."),
    ]:
        db.session.add(StockNote(security=by_t.get(t) if t else None, title=title, body=body, author=rnd.choice([users["marcus"], users["tirumala"], users["sofia"]]),
                                 pinned=rnd.random() < .3))

    drivers = []
    for code, name, kind, val in [("US10Y", "US 10-year yield", "RATES", 4.21), ("AI-CAPEX", "AI capex momentum", "THEMATIC", 118.0),
                                  ("VIX", "Equity volatility", "RISK", 17.6), ("MTUM", "Momentum factor", "EQUITY_FACTOR", 212.4),
                                  ("WTI", "Crude oil", "COMMODITY", 71.3), ("DXY", "US dollar index", "FX", 104.2),
                                  ("GOLD", "Gold spot", "COMMODITY", 2611.0), ("HY-OAS", "High-yield spread", "CREDIT", 3.1),
                                  ("QUAL", "Quality factor", "EQUITY_FACTOR", 178.9), ("SOX", "Semiconductor cycle", "THEMATIC", 5120.0)]:
        d = Driver(code=code, name=name, kind=kind, value=val, change_1d=round(rnd.gauss(0, 2.4), 2))
        d.zscore = round(abs(d.change_1d) / 1.2, 1)
        drivers.append(d)
        db.session.add(d)
    db.session.flush()
    for d in drivers:
        for s in rnd.sample(secs[:len(held)], rnd.randint(4, 12)):
            db.session.add(DriverExposure(driver=d, security=s, beta=round(rnd.uniform(-1.2, 1.6), 2)))

    for i, (code, name, val) in enumerate([("SPX", "S&P 500", 6104.2), ("DJI", "Dow Jones", 44120.5), ("IXIC", "Nasdaq", 19804.7),
                                           ("RUT", "Russell 2000", 2391.4), ("VIX", "VIX", 17.6), ("TNX", "10Y Treasury", 4.21),
                                           ("SX5E", "Euro Stoxx 50", 5012.8), ("N225", "Nikkei 225", 39470.3)]):
        db.session.add(MarketIndex(code=code, name=name, value=val, change_pct=round(rnd.gauss(0.05, .7), 2), sort=i))

    for t, kind, dd, detail, st in [("AVGO", "Dividend", 12, "$0.59 quarterly dividend", "Pending"), ("WMT", "Split", -40, "3-for-1 stock split", "Processed"),
                                    ("GE", "Spin-off", -180, "GE Vernova spin, 1 GEV per 4 GE", "Processed"), ("JPM", "Dividend", 5, "$1.25 quarterly dividend", "Pending"),
                                    ("COST", "Special dividend", 30, "$15.00 special dividend", "Pending"), ("NVDA", "Split", -150, "10-for-1 stock split", "Processed"),
                                    ("XOM", "Dividend", 18, "$0.99 quarterly dividend", "Pending"), ("BX", "Tender", 9, "Odd-lot tender offer", "Pending")]:
        db.session.add(CorporateAction(security=by_t[t], kind=kind, ex_date=today + timedelta(days=dd), detail=detail, status=st))
    db.session.flush()

    # yesterday's review snapshot (slightly different so 'new problems' / 'cleared' is non-empty)
    pos = positions()
    long_mv = sum(p.mv for p in pos)
    for p in pos:
        probs, _ = problems_for(p, long_mv)
        if probs and rnd.random() < .3:
            probs = probs[1:]
        elif rnd.random() < .08:
            probs = probs + ["Momentum"]
        db.session.add(ReviewSnapshot(day=today - timedelta(days=1), ticker=p.security.ticker, problems=",".join(probs)))

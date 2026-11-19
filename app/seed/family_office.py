"""Family office ledger, real estate and private investments (shared by FO, RE, PE/VC, IR)."""
from datetime import date, timedelta

from ..extensions import db
from ..models import (Entity, Investment, Distribution, CapitalCall, Valuation, Property, PropertyMonth, Loan, Metro,
                      REIssue, Exchange1031, BankAccount, CashTxn, Bill, RecurringCash, FamilyObligation, Wire,
                      TreasuryHolding, SharedExpense, CloseTask, InsurancePolicy, Vendor, PersonalAsset, Contract,
                      LegalDocument, LegalMatter, ReportRun, TaxFiling, K1, EstimatedTax, ComplianceItem)

ENTITIES = [
    # name, kind, parent, pct, jurisdiction, purpose
    ("Alladin Family Trust", "Trust", None, 100, "SD", "Top-level dynasty trust holding family assets"),
    ("Alladin Holdings LLC", "LLC", "Alladin Family Trust", 100, "DE", "Operating holding company; employs office staff"),
    ("Alladin Growth Trust", "Trust", "Alladin Family Trust", 100, "SD", "Long-horizon growth assets for the next generation"),
    ("Alladin Real Estate LP", "LP", "Alladin Holdings LLC", 100, "DE", "Owns property-level SPVs"),
    ("Alladin Ventures LLC", "LLC", "Alladin Growth Trust", 100, "DE", "Venture and growth equity commitments"),
    ("Alladin Credit Partners LP", "LP", "Alladin Holdings LLC", 100, "DE", "Private credit and notes receivable"),
    ("Alladin Foundation", "Foundation", None, 100, "NC", "Private foundation; grants via donor-advised fund"),
    ("Tirumala", "Individual", None, 100, "NC", "Principal"),
    ("Kaveri Alladin 2019 Trust", "Trust", "Alladin Family Trust", 100, "SD", "GST-exempt trust for children"),
    ("Alladin Aviation LLC", "LLC", "Alladin Holdings LLC", 100, "DE", "Fractional aircraft interest and related costs"),
]

METROS = [("Raleigh", "NC", 2.1, 4.4, 2.6, 6.2, 3.1), ("Dallas", "TX", 1.8, 2.9, 2.2, -4.5, 1.2), ("Charleston", "SC", 2.4, 5.1, 2.9, 11.8, 3.9),
          ("Boise", "ID", 1.7, 1.2, 1.4, -12.6, -0.4), ("Atlanta", "GA", 1.3, 3.3, 1.6, 2.4, 0.8), ("Phoenix", "AZ", 1.6, 1.9, 1.9, -8.1, -1.2),
          ("Tampa", "FL", 1.9, -0.8, 1.7, -14.2, -0.6), ("Nashville", "TN", 2.0, 3.8, 2.4, 8.7, 2.2), ("Denver", "CO", 0.8, 0.6, 0.9, -19.4, -1.9),
          ("Austin", "TX", 2.6, -2.1, 2.8, -22.3, -3.4), ("Savannah", "GA", 1.4, 4.0, 1.5, 16.9, 2.8), ("Salt Lake City", "UT", 1.5, 3.1, 2.0, 4.1, 1.6),
          ("Charlotte", "NC", 2.2, 4.6, 2.5, 9.3, 2.9)]

PROPS = [
    # name, kind, city, state, units, sqft, price, acquired_years_ago, fmv_mult, occ
    ("Cedar Bluff Apartments", "Multifamily", "Raleigh", "NC", 240, 214000, 38_500_000, 5.2, 1.34, 94.6),
    ("Ironwood Logistics Park", "Industrial", "Dallas", "TX", None, 410000, 41_200_000, 3.8, 1.21, 100.0),
    ("Palmetto Row Townhomes", "Multifamily", "Charleston", "SC", 96, 112000, 17_900_000, 2.6, 1.18, 92.1),
    ("Silver Creek Self Storage", "Self-storage", "Boise", "ID", 640, 78000, 9_800_000, 4.1, 1.09, 86.4),
    ("Magnolia Commons", "Retail", "Atlanta", "GA", 22, 96000, 21_600_000, 6.5, 0.94, 89.0),
    ("Copperline Flats", "Multifamily", "Phoenix", "AZ", 180, 152000, 29_400_000, 2.1, 0.97, 91.3),
    ("Bayview Medical Offices", "Office", "Tampa", "FL", 14, 64000, 15_200_000, 7.0, 0.88, 82.5),
    ("Riverbend Industrial", "Industrial", "Nashville", "TN", None, 265000, 24_800_000, 1.6, 1.12, 97.0),
    ("Highland Park Lofts", "Multifamily", "Denver", "CO", 120, 98000, 26_100_000, 3.3, 0.91, 90.2),
    ("Oakmont Village", "Multifamily", "Austin", "TX", 210, 188000, 36_800_000, 2.9, 0.86, 88.7),
    ("Seaside Inn & Suites", "Hospitality", "Savannah", "GA", 118, 71000, 18_300_000, 4.8, 1.16, 76.0),
    ("Westgate Flex Center", "Industrial", "Salt Lake City", "UT", None, 132000, 13_700_000, 1.2, 1.05, 95.5),
    ("Pinecrest Land Parcel", "Land", "Charlotte", "NC", None, None, 6_400_000, 1.9, 1.22, None),
]

COORD = {"Raleigh": (35.78, -78.64), "Dallas": (32.78, -96.8), "Charleston": (32.78, -79.93), "Boise": (43.62, -116.2), "Atlanta": (33.75, -84.39),
         "Phoenix": (33.45, -112.07), "Tampa": (27.95, -82.46), "Nashville": (36.16, -86.78), "Denver": (39.74, -104.99), "Austin": (30.27, -97.74),
         "Savannah": (32.08, -81.09), "Salt Lake City": (40.76, -111.89), "Charlotte": (35.23, -80.84), "San Francisco": (37.77, -122.42),
         "New York": (40.71, -74.0), "Boston": (42.36, -71.06), "Chicago": (41.88, -87.63), "Seattle": (47.61, -122.33), "Miami": (25.76, -80.19),
         "Los Angeles": (34.05, -118.24), "Minneapolis": (44.98, -93.27), "Columbus": (39.96, -83.0), "Pittsburgh": (40.44, -79.99)}

# name, asset_class, deal_type, sector, vintage, invested_k, nav_mult, dist_mult, city
PRIVATE = [
    ("Kestrel Analytics — Series B", "Venture Capital", "Growth", "Software", 2021, 4200, 1.42, 0.0, "Boston"),
    ("Tidewater Capital Fund IV", "Private Equity", "Fund", "Diversified", 2019, 9600, 1.18, 0.62, "New York"),
    ("Granary Foods Buyout", "Private Equity", "Buyout", "Consumer", 2020, 7400, 1.31, 0.35, "Chicago"),
    ("Halcyon Health Partners", "Private Equity", "Buyout", "Healthcare", 2022, 6800, 1.12, 0.08, "Nashville"),
    ("Brightwater Dental Group", "Private Equity", "Co-Invest", "Healthcare", 2023, 5100, 1.24, 0.0, "Charlotte"),
    ("Ferrum Industrial Services", "Private Equity", "Buyout", "Industrials", 2021, 8200, 1.47, 0.22, "Pittsburgh"),
    ("Sable Ridge Growth II", "Private Equity", "Fund", "Growth", 2020, 11000, 1.64, 0.41, "San Francisco"),
    ("Orchid Payments", "Venture Capital", "Growth", "Fintech", 2021, 3500, 0.71, 0.0, "New York"),
    ("Quarry Lane Packaging", "Private Equity", "Co-Invest", "Industrials", 2022, 6200, 1.09, 0.05, "Columbus"),
    ("Lattice Robotics — Series A", "Venture Capital", "Early Stage", "Robotics", 2023, 1800, 1.35, 0.0, "Pittsburgh"),
    ("Meridian Water Infrastructure", "Private Equity", "Co-Invest", "Infrastructure", 2021, 7600, 1.22, 0.31, "Phoenix"),
    ("Tallgrass Ag Partners", "Private Equity", "Fund", "Agriculture", 2018, 5000, 1.05, 0.88, "Minneapolis"),
    ("Coral Bay Hospitality Fund", "Private Equity", "Fund", "Hospitality", 2019, 4500, 0.92, 0.34, "Miami"),
    ("Northgate Software Holdings", "Private Equity", "Buyout", "Software", 2022, 9800, 1.29, 0.0, "Seattle"),
    ("Pioneer Veterinary Partners", "Private Equity", "Buyout", "Healthcare", 2020, 5600, 1.71, 0.52, "Denver"),
    ("Vela Climate — Seed", "Venture Capital", "Early Stage", "Climate", 2024, 750, 1.0, 0.0, "San Francisco"),
    ("Ember Security — Series C", "Venture Capital", "Growth", "Cybersecurity", 2022, 2600, 1.18, 0.0, "Seattle"),
    ("Summit Arch Capital III", "Private Equity", "Fund", "Diversified", 2023, 6000, 1.07, 0.0, "New York"),
    ("Cobalt Freight Systems", "Private Equity", "Co-Invest", "Logistics", 2021, 4800, 0.83, 0.0, "Dallas"),
    ("Juno Learning — Series B", "Venture Capital", "Growth", "Education", 2021, 2200, 0.58, 0.0, "Austin"),
    ("Harrow Specialty Pharma", "Private Equity", "Buyout", "Healthcare", 2019, 6500, 1.92, 1.1, "Boston"),
    ("Stonefield Building Products", "Private Equity", "Buyout", "Industrials", 2018, 5200, 1.38, 1.24, "Atlanta"),
    ("Aurora Biologics — Series B", "Venture Capital", "Growth", "Biotech", 2022, 3000, 1.55, 0.0, "Boston"),
    ("Keystone Insurance Services", "Private Equity", "Co-Invest", "Financial Services", 2023, 5400, 1.16, 0.0, "Philadelphia"),
    ("Westbrook Lower Mid-Market V", "Private Equity", "Fund", "Diversified", 2021, 7000, 1.26, 0.18, "Chicago"),
    ("Pelican Marine Services", "Private Equity", "Buyout", "Industrials", 2024, 4300, 1.02, 0.0, "Tampa"),
    ("Driftwood Data — Series A", "Venture Capital", "Early Stage", "Software", 2024, 1200, 1.1, 0.0, "New York"),
    ("Canopy Home Services", "Private Equity", "Co-Invest", "Consumer Services", 2022, 5900, 1.33, 0.06, "Raleigh"),
    ("Basalt Energy Transition II", "Private Equity", "Fund", "Energy", 2022, 6500, 1.11, 0.04, "Denver"),
    ("Nimbus Logistics Software", "Venture Capital", "Growth", "Software", 2023, 2500, 1.27, 0.0, "Atlanta"),
    ("Redwood Pediatric Therapy", "Private Equity", "Buyout", "Healthcare", 2021, 6100, 1.44, 0.15, "Charlotte"),
    ("Arbor Specialty Chemicals", "Private Equity", "Co-Invest", "Materials", 2020, 4700, 0.97, 0.21, "Columbus"),
    ("Polaris Mobility — Series B", "Venture Capital", "Growth", "Mobility", 2021, 2800, 0.46, 0.0, "Los Angeles"),
    ("Granite Peak Secondaries", "Private Equity", "Fund", "Secondaries", 2023, 5500, 1.19, 0.12, "New York"),
    ("Fathom Ocean Tech — Seed", "Venture Capital", "Early Stage", "Climate", 2024, 600, 1.0, 0.0, "San Francisco"),
    ("Linden Wealth Platforms", "Private Equity", "Buyout", "Financial Services", 2023, 7200, 1.21, 0.0, "Chicago"),
    ("Tessellate AI — Series A", "Venture Capital", "Early Stage", "AI", 2025, 1500, 1.6, 0.0, "San Francisco"),
]

CREDIT = [("Blue Heron Direct Lending II", 6_000_000, 6_180_000, 1_420_000), ("Mesa Senior Loan Fund", 4_500_000, 4_610_000, 980_000),
          ("Harbor Mezz — Hotel Refinance", 3_200_000, 3_200_000, 610_000), ("Equipment Notes Program", 2_400_000, 2_330_000, 520_000),
          ("Bridge Loan — Palmer Industrial", 2_800_000, 2_800_000, 340_000), ("Asset-Based Credit Fund I", 5_000_000, 5_240_000, 760_000),
          ("Specialty Finance SMA", 3_500_000, 3_420_000, 430_000)]
OTHER = [("Pinnacle Multi-Strategy Fund", "Hedge Funds", 8_000_000, 9_140_000), ("Global Macro Partners", "Hedge Funds", 5_000_000, 5_310_000),
         ("Fine Art Collection", "Alternative Investments", 3_100_000, 4_200_000), ("Aircraft Fractional Share", "Alternative Investments", 2_600_000, 1_900_000)]


def months_back(n):
    d = date.today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d)
        d = (d - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def seed(ctx):
    rnd = ctx["rnd"]
    users = ctx["users"]
    today = date.today()
    ents = {}
    for name, kind, parent, pct, jur, purpose in ENTITIES:
        e = Entity(name=name, kind=kind, parent=ents.get(parent), ownership_pct=pct, jurisdiction=jur, purpose=purpose,
                   ein_hint=f"**-***{rnd.randint(1000, 9999)}" if kind != "Individual" else None,
                   formed=date(rnd.randint(2004, 2020), rnd.randint(1, 12), rnd.randint(1, 28)),
                   manager="Alladin Holdings LLC" if kind in ("LLC", "LP") else "Tirumala")
        ents[name] = e
        db.session.add(e)
    db.session.flush()
    ctx["entities"] = ents

    for m in METROS:
        name, st, pop, hpi, emp, permits, rent = m
        score = int(50 + pop * 6 + hpi * 2 + emp * 3 + rent * 2 + rnd.uniform(-3, 3))
        db.session.add(Metro(name=name, state=st, pop_yoy=pop, hpi_yoy=hpi, emp_yoy=emp, permits_yoy=permits, rent_yoy=rent, score=min(score, 95)))

    # ---------- real estate
    re_ent = ents["Alladin Real Estate LP"]
    props = []
    for (name, kind, city, st, units, sqft, price, yrs, mult, occ) in PROPS:
        acq = today - timedelta(days=int(yrs * 365))
        fmv = round(price * mult, -4)
        rev = price * rnd.uniform(.085, .12) if kind != "Land" else 0
        opex = rev * rnd.uniform(.36, .52)
        noi = rev - opex
        inv = Investment(name=name, entity=re_ent, asset_class="Real Estate", deal_type="Direct", sponsor="Alladin Real Estate LP", sector=kind,
                         vintage=acq.year, commitment=price * .35, invested=round(price * .35, -3), fmv=0, distributions=0, city=city, state=st,
                         lat=COORD[city][0] + rnd.uniform(-.05, .05), lon=COORD[city][1] + rnd.uniform(-.05, .05), target_irr=rnd.choice([12, 14, 15, 16]),
                         target_moic=rnd.choice([1.7, 1.8, 2.0]), hold_years=rnd.choice([5, 7, 10]), pref_return=8, promote=20, mgmt_fee=1.0,
                         last_mark=today - timedelta(days=rnd.randint(20, 80)))
        p = Property(name=name, entity=re_ent, investment=inv, kind=kind, address=f"{rnd.randint(100, 9800)} {rnd.choice(['Oak', 'Main', 'Commerce', 'Harbor', 'Ridge', 'Market', 'Lake'])} {rnd.choice(['St', 'Blvd', 'Pkwy', 'Dr', 'Way'])}",
                     city=city, state=st, metro=city, units=units, sqft=sqft, purchase_price=price, acquired=acq, fmv=fmv,
                     noi_t12=round(noi, -2), revenue_t12=round(rev, -2), opex_t12=round(opex, -2), occupancy=occ,
                     capex_budget=round(price * rnd.uniform(.005, .02), -3), cap_rate_uw=round(rnd.uniform(5.0, 6.8), 2),
                     noi_uw=round(noi * rnd.uniform(.92, 1.12), -2), status="Development" if kind == "Land" else "Operating",
                     manager=rnd.choice(["Greystar-style PM (3rd party)", "In-house", "Cardinal Property Mgmt", "Summit Asset Services"]))
        db.session.add_all([inv, p])
        props.append(p)
        if kind != "Land":
            ltv = rnd.uniform(.5, .66)
            bal = round(fmv * ltv, -4)
            rate = round(rnd.uniform(3.6, 7.2), 2)
            mat = today + timedelta(days=rnd.randint(70, 2400))
            ds = round(bal * (rate / 100 + (0.012 if rnd.random() < .6 else 0)), -2)
            db.session.add(Loan(name=f"{name} — senior mortgage", kind="Mortgage", direction="payable", lender=rnd.choice(["Wells Fargo", "Truist", "PNC", "Freddie Mac", "Pacific Life", "Regions"]),
                                borrower=f"{name} SPV LLC", entity=re_ent, property=p, principal=round(bal * 1.04, -4), balance=bal, rate=rate,
                                rate_type=rnd.choice(["Fixed", "Fixed", "Floating"]), originated=acq, maturity=mat, annual_debt_service=ds,
                                dscr_covenant=rnd.choice([1.20, 1.25, 1.30])))
        # 24 months of operating history
        for i, mth in enumerate(months_back(24)):
            if kind == "Land":
                break
            seasonal = 1 + .04 * ((mth.month in (6, 7, 8)) - (mth.month in (1, 2)))
            r = rev / 12 * seasonal * (0.93 + i * 0.004) * rnd.uniform(.97, 1.03)
            o = opex / 12 * rnd.uniform(.9, 1.12)
            db.session.add(PropertyMonth(property=p, month=mth, revenue=round(r, -1), opex=round(o, -1), noi=round(r - o, -1),
                                         occupancy=round(min(100, (occ or 90) + rnd.uniform(-3, 2)), 1), reviewed=i < 21))
    db.session.flush()
    for p in props:
        p.investment.fmv = round((p.fmv - p.debt) * (p.ownership_pct / 100), -3)
        p.investment.distributions = round(p.investment.invested * rnd.uniform(.05, .45), -3)
    ctx["properties"] = props

    # ---------- private investments
    invs = []
    pe_ent = {"Venture Capital": ents["Alladin Ventures LLC"], "Private Equity": ents["Alladin Growth Trust"]}
    for name, ac, dt, sector, vin, inv_k, navm, distm, city in PRIVATE:
        if inv_k == 0:
            continue
        invested = inv_k * 1000
        commit = round(invested / rnd.uniform(.7, 1.0) if dt == "Fund" else invested, -4)
        i = Investment(name=name, entity=pe_ent[ac], asset_class=ac, deal_type=dt, sponsor=rnd.choice(["Tidewater", "Sable Ridge", "Westbrook", "Summit Arch", "Lantern Peak", "Blue Ledger", "Direct"]) if dt != "Fund" else name.split(" ")[0] + " Capital",
                       sector=sector, vintage=vin, commitment=commit, invested=invested, fmv=round(invested * navm, -3), distributions=round(invested * distm, -3),
                       city=city, state=None, lat=COORD.get(city, (39.95, -75.16))[0] + rnd.uniform(-.08, .08), lon=COORD.get(city, (39.95, -75.16))[1] + rnd.uniform(-.08, .08),
                       target_irr=rnd.choice([18, 20, 22, 25, 30]) if ac == "Venture Capital" else rnd.choice([15, 17, 18, 20]),
                       target_moic=rnd.choice([2.0, 2.5, 3.0]), hold_years=rnd.choice([4, 5, 6, 7]), pref_return=8, promote=20, mgmt_fee=rnd.choice([1.5, 2.0, 0, 1.0]),
                       last_mark=today - timedelta(days=rnd.choice([12, 40, 75, 100, 140, 200])))
        if navm < .75:
            i.attention = "Marked below 0.75x — request updated plan from sponsor"
            i.review_status = "Watch"
        elif (today - i.last_mark).days > 120:
            i.attention = "Stale mark — no valuation received in over 120 days"
        invs.append(i)
        db.session.add(i)
    for name, inv, fmv, dist in CREDIT:
        db.session.add(Investment(name=name, entity=ents["Alladin Credit Partners LP"], asset_class="Private Credit", deal_type="Direct", sector="Credit",
                                  vintage=rnd.randint(2020, 2024), commitment=inv, invested=inv, fmv=fmv, distributions=dist, target_irr=11, last_mark=today - timedelta(days=30)))
    for name, ac, inv, fmv in OTHER:
        db.session.add(Investment(name=name, entity=ents["Alladin Holdings LLC"], asset_class=ac, deal_type="Direct", sector=ac, vintage=rnd.randint(2016, 2022),
                                  commitment=inv, invested=inv, fmv=fmv, distributions=0, marketable=ac == "Hedge Funds", last_mark=today - timedelta(days=45)))
    for name, ent, inv, fmv in [("Schwab equity sleeve", "Alladin Family Trust", 52_000_000, 0), ("Fidelity growth sleeve", "Alladin Growth Trust", 31_000_000, 0),
                                ("IBKR concentrated sleeve", "Alladin Holdings LLC", 26_000_000, 0)]:
        db.session.add(Investment(name=name, entity=ents[ent], asset_class="Public Equities", deal_type="Separate account", sector="Public markets",
                                  vintage=2015, commitment=inv, invested=inv, fmv=fmv, marketable=True, notes="FMV is pulled live from the Stocks app"))
    sold = [("Lakewood Senior Living", "Real Estate", 2016, 6_200_000, 11_900_000, today - timedelta(days=410)),
            ("Brightline Pet Brands", "Private Equity", 2017, 4_000_000, 9_600_000, today - timedelta(days=640)),
            ("Copper Basin Apartments", "Real Estate", 2015, 5_100_000, 8_700_000, today - timedelta(days=900)),
            ("Signal Hill Software", "Venture Capital", 2018, 1_500_000, 6_300_000, today - timedelta(days=300)),
            ("Fairway Storage Portfolio", "Real Estate", 2017, 3_800_000, 5_200_000, today - timedelta(days=150))]
    for name, ac, vin, inv, proceeds, sd in sold:
        db.session.add(Investment(name=name, entity=ents["Alladin Holdings LLC"], asset_class=ac, deal_type="Direct", vintage=vin, commitment=inv, invested=inv,
                                  fmv=0, distributions=proceeds, status="Sold", sold_on=sd, sector=ac))
    db.session.flush()
    ctx["private"] = invs

    # distributions, calls, valuations
    all_inv = Investment.query.filter(Investment.status == "Active", Investment.asset_class.notin_(["Public Equities"])).all()
    for i in all_inv:
        total = i.distributions or 0
        n = rnd.randint(2, 8) if total else 0
        for k in range(n):
            db.session.add(Distribution(investment=i, day=today - timedelta(days=rnd.randint(5, 720)), amount=round(total / n, 2),
                                        kind=rnd.choice(["Income", "Return of capital", "Gain"]), tied_out=rnd.random() < .7))
        if i.asset_class in ("Private Equity", "Venture Capital"):
            for q in range(rnd.randint(2, 6)):
                d = (i.last_mark or today) - timedelta(days=91 * q)
                db.session.add(Valuation(investment=i, day=d, fmv=round(i.fmv * (1 - .03 * q + rnd.uniform(-.02, .02)), -3), method=rnd.choice(["GP statement", "GP statement", "Mark-to-model", "Recent round"])))
            if i.unfunded > 0:
                db.session.add(CapitalCall(investment=i, notice_date=today - timedelta(days=rnd.randint(2, 20)), due=today + timedelta(days=rnd.randint(3, 40)),
                                           amount=round(min(i.unfunded, i.commitment * rnd.uniform(.05, .15)), -3), status="Pending"))
            for q in range(rnd.randint(1, 4)):
                db.session.add(CapitalCall(investment=i, notice_date=today - timedelta(days=200 + 120 * q), due=today - timedelta(days=185 + 120 * q),
                                           amount=round(i.invested * rnd.uniform(.1, .25), -3), status="Paid"))

    # ---------- loans (non-mortgage)
    db.session.add_all([
        Loan(name="Note receivable — Palmer Industrial bridge", kind="Note receivable", direction="receivable", lender="Alladin Credit Partners LP", borrower="Palmer Industrial Holdings",
             entity=ents["Alladin Credit Partners LP"], principal=2_800_000, balance=2_800_000, rate=11.0, originated=today - timedelta(days=200), maturity=today + timedelta(days=165), annual_debt_service=308_000),
        Loan(name="Note receivable — family member home loan", kind="Note receivable", direction="receivable", lender="Alladin Family Trust", borrower="R. Alladin",
             entity=ents["Alladin Family Trust"], principal=1_200_000, balance=1_046_000, rate=4.27, originated=today - timedelta(days=900), maturity=today + timedelta(days=4500), annual_debt_service=74_000),
        Loan(name="Seller note — Brightline Pet Brands", kind="Note receivable", direction="receivable", lender="Alladin Holdings LLC", borrower="Brightline Acquisition Co",
             entity=ents["Alladin Holdings LLC"], principal=1_500_000, balance=900_000, rate=8.0, originated=today - timedelta(days=640), maturity=today + timedelta(days=455), annual_debt_service=420_000, status="Watch"),
        Loan(name="Securities-based line — Schwab", kind="Line of credit", direction="payable", lender="Charles Schwab Bank", borrower="Alladin Family Trust",
             entity=ents["Alladin Family Trust"], principal=10_000_000, balance=3_400_000, rate=6.35, rate_type="Floating", originated=today - timedelta(days=700), maturity=today + timedelta(days=330), annual_debt_service=215_900),
        Loan(name="Aircraft loan", kind="Note payable", direction="payable", lender="Bank of the Carolinas", borrower="Alladin Aviation LLC",
             entity=ents["Alladin Aviation LLC"], principal=1_800_000, balance=1_120_000, rate=5.1, originated=today - timedelta(days=1300), maturity=today + timedelta(days=1100), annual_debt_service=290_000),
        Loan(name="Intercompany — Holdings to Real Estate LP", kind="Intercompany", direction="receivable", lender="Alladin Holdings LLC", borrower="Alladin Real Estate LP",
             entity=ents["Alladin Holdings LLC"], counterparty_entity=ents["Alladin Real Estate LP"], principal=4_500_000, balance=3_850_000, rate=4.5, originated=today - timedelta(days=800), maturity=today + timedelta(days=1000)),
        Loan(name="Intercompany — Family Trust to Ventures", kind="Intercompany", direction="receivable", lender="Alladin Family Trust", borrower="Alladin Ventures LLC",
             entity=ents["Alladin Family Trust"], counterparty_entity=ents["Alladin Ventures LLC"], principal=6_000_000, balance=6_000_000, rate=4.1, originated=today - timedelta(days=420), maturity=today + timedelta(days=2500)),
        Loan(name="Intercompany — Holdings to Aviation", kind="Intercompany", direction="receivable", lender="Alladin Holdings LLC", borrower="Alladin Aviation LLC",
             entity=ents["Alladin Holdings LLC"], counterparty_entity=ents["Alladin Aviation LLC"], principal=750_000, balance=610_000, rate=4.5, originated=today - timedelta(days=500), maturity=today + timedelta(days=600)),
    ])

    db.session.add_all([
        Exchange1031(relinquished="Fairway Storage Portfolio", replacement="Westgate Flex Center", sale_date=today - timedelta(days=150), proceeds=5_200_000, qi="First American Exchange", status="Identified"),
        Exchange1031(relinquished="Copper Basin Apartments", replacement="Riverbend Industrial", sale_date=today - timedelta(days=900), proceeds=8_700_000, qi="IPX1031", status="Complete"),
    ])

    # ---------- cash
    banks = []
    for name, inst, ent, kind, bal, rate in [
        ("Holdings operating", "First Citizens", "Alladin Holdings LLC", "Operating", 1_840_000, 0.5), ("Holdings money market", "First Citizens", "Alladin Holdings LLC", "Money market", 4_200_000, 4.1),
        ("Family Trust operating", "JPMorgan", "Alladin Family Trust", "Operating", 960_000, 0.2), ("Family Trust treasury", "JPMorgan", "Alladin Family Trust", "Treasury", 6_800_000, 4.4),
        ("Real Estate LP operating", "Truist", "Alladin Real Estate LP", "Operating", 1_310_000, 0.3), ("Real Estate reserves", "Truist", "Alladin Real Estate LP", "Escrow", 2_240_000, 3.2),
        ("Ventures operating", "Silicon Valley Bank", "Alladin Ventures LLC", "Operating", 720_000, 0.4), ("Credit Partners operating", "PNC", "Alladin Credit Partners LP", "Operating", 1_050_000, 0.4),
        ("Foundation operating", "Bank of America", "Alladin Foundation", "Operating", 410_000, 0.1), ("Personal checking", "JPMorgan", "Tirumala", "Operating", 285_000, 0.0),
        ("Aviation operating", "First Citizens", "Alladin Aviation LLC", "Operating", 140_000, 0.0)]:
        ba = BankAccount(name=name, institution=inst, entity=ents[ent], kind=kind, last4=str(rnd.randint(1000, 9999)), balance=bal, rate=rate,
                         min_balance=round(bal * .1, -4), statement_balance=bal)
        banks.append(ba)
        db.session.add(ba)
    db.session.flush()
    cats_in = [("Distribution", "fund"), ("Rent / NOI sweep", "property"), ("Interest income", "bank"), ("Note payment received", "note")]
    cats_out = [("Payroll", "Gusto"), ("Professional fees", "Hale & Whitlock LLP"), ("Capital call", "fund"), ("Insurance", "Chubb"), ("Property tax", "County Tax Collector"),
                ("Travel", "NetJets"), ("Household", "Estate staff"), ("Software", "Various SaaS"), ("Charitable", "Alladin Foundation DAF"), ("Debt service", "Lender")]
    pnames = [p.name for p in props] + [i.name for i in invs[:12]]
    for k in range(560):
        ba = rnd.choice(banks)
        d = today - timedelta(days=rnd.randint(0, 365))
        if rnd.random() < .42:
            cat, cp = rnd.choice(cats_in)
            amt = round(rnd.uniform(4_000, 420_000), 2)
        else:
            cat, cp = rnd.choice(cats_out)
            amt = -round(rnd.uniform(800, 260_000), 2)
        if cp in ("fund", "property", "note"):
            cp = rnd.choice(pnames)
        db.session.add(CashTxn(bank_account=ba, day=d, amount=amt, category=cat, counterparty=cp,
                               memo=f"{cat} — {d:%b %Y}", reconciled=(today - d).days > 25 or rnd.random() < .4))
    for payee, cat, ent, amt, dd, st in [
        ("Chubb Personal Risk", "Insurance", "Alladin Holdings LLC", 48_200, 4, "Open"), ("Mecklenburg County", "Property tax", "Alladin Real Estate LP", 128_400, 12, "Approved"),
        ("Hale & Whitlock LLP", "Legal", "Alladin Family Trust", 22_850, -6, "Open"), ("Cardinal Property Mgmt", "Property management", "Alladin Real Estate LP", 18_300, 2, "Open"),
        ("Duke Energy", "Utilities", "Alladin Holdings LLC", 3_120, -2, "Open"), ("Altitude Jet Services", "Aviation", "Alladin Aviation LLC", 36_900, 9, "Open"),
        ("Ridgeway CPA Group", "Tax prep", "Alladin Holdings LLC", 41_000, 21, "Open"), ("Northbridge IT", "Technology", "Alladin Holdings LLC", 6_480, 1, "Approved"),
        ("Oakline Landscaping", "Household", "Tirumala", 2_650, -12, "Open"), ("Sterling Security", "Household", "Tirumala", 4_900, 6, "Open"),
        ("Wake County", "Property tax", "Alladin Real Estate LP", 96_700, 35, "Open"), ("Apex Elevator Co", "Repairs", "Alladin Real Estate LP", 11_250, 15, "Open"),
        ("Gusto", "Payroll", "Alladin Holdings LLC", 86_000, 3, "Approved"), ("Iron Mountain", "Records", "Alladin Holdings LLC", 840, 18, "Open")]:
        db.session.add(Bill(payee=payee, category=cat, entity=ents[ent], amount=amt, due=today + timedelta(days=dd), status=st))
    for k in range(26):
        db.session.add(Bill(payee=rnd.choice(["Gusto", "Chubb Personal Risk", "Duke Energy", "Hale & Whitlock LLP", "Cardinal Property Mgmt", "Northbridge IT"]),
                            category="Recurring", entity=rnd.choice(list(ents.values())), amount=round(rnd.uniform(800, 90_000), 2),
                            due=today - timedelta(days=rnd.randint(20, 300)), status="Paid", paid_on=today - timedelta(days=rnd.randint(15, 290))))
    for name, ent, dirn, amt, freq, nd, cat in [
        ("Office payroll", "Alladin Holdings LLC", "out", 86_000, "Semi-monthly", 3, "Payroll"), ("Office lease — Raleigh", "Alladin Holdings LLC", "out", 24_500, "Monthly", 11, "Rent"),
        ("Cedar Bluff NOI sweep", "Alladin Real Estate LP", "in", 192_000, "Monthly", 8, "Rent / NOI sweep"), ("Ironwood NOI sweep", "Alladin Real Estate LP", "in", 214_000, "Monthly", 9, "Rent / NOI sweep"),
        ("Schwab line interest", "Alladin Family Trust", "out", 18_000, "Monthly", 14, "Interest"), ("Blue Heron quarterly distribution", "Alladin Credit Partners LP", "in", 150_000, "Quarterly", 40, "Distribution"),
        ("Foundation DAF funding", "Alladin Foundation", "out", 125_000, "Quarterly", 25, "Charitable"), ("Aircraft management fee", "Alladin Aviation LLC", "out", 31_000, "Monthly", 6, "Aviation"),
        ("Umbrella insurance premium", "Alladin Holdings LLC", "out", 96_000, "Annual", 70, "Insurance"), ("Family member note payment", "Alladin Family Trust", "in", 6_150, "Monthly", 1, "Note payment received"),
        ("Household staff", "Tirumala", "out", 28_000, "Monthly", 5, "Household"), ("Tuition — upper school", "Tirumala", "out", 21_400, "Semi-annual", 52, "Education")]:
        db.session.add(RecurringCash(name=name, entity=ents[ent], direction=dirn, amount=amt, frequency=freq, next_date=today + timedelta(days=nd), category=cat))
    for person, desc, amt, freq, nd, src in [("Kaveri Alladin", "Monthly allowance", 6_000, "Monthly", 4, "Personal checking"), ("Arjun Alladin", "University tuition & housing", 38_500, "Semi-annual", 48, "Kaveri Alladin 2019 Trust"),
                                             ("Lakshmi Alladin", "Medical & care support", 9_200, "Monthly", 10, "Alladin Family Trust"), ("Ravi Alladin", "Home loan servicing (receivable)", 6_150, "Monthly", 1, "Family Trust operating"),
                                             ("Extended family", "Annual gifts (exclusion)", 216_000, "Annual", 40, "Personal checking"), ("Kaveri Alladin", "Car lease", 1_450, "Monthly", 17, "Personal checking")]:
        db.session.add(FamilyObligation(person=person, description=desc, amount=amt, frequency=freq, next_date=today + timedelta(days=nd), paid_from=src))
    for k, (ben, amt, purpose, st) in enumerate([("Summit Arch Capital III", 420_000, "Capital call #4", "Pending approval"), ("Basalt Energy Transition II", 315_000, "Capital call #6", "Approved"),
                                                 ("First American Exchange", 1_200_000, "1031 replacement deposit", "Sent"), ("Ridgeway CPA Group", 41_000, "Tax prep retainer", "Draft"),
                                                 ("Granite Peak Secondaries", 550_000, "Capital call #2", "Sent"), ("Altitude Jet Services", 36_900, "Q4 management", "Pending approval"),
                                                 ("Westbrook Lower Mid-Market V", 280_000, "Capital call #9", "Sent"), ("Mecklenburg County", 128_400, "Property tax", "Approved")]):
        db.session.add(Wire(day=today - timedelta(days=k * 4), bank_account=banks[k % 4], beneficiary=ben, bank=rnd.choice(["JPMorgan Chase", "Citibank", "Wells Fargo", "BNY"]),
                            amount=amt, purpose=purpose, status=st, requested_by=users["elena"], approved_by=users["priya"] if st in ("Approved", "Sent") else None))
    for k in range(8):
        mat = today + timedelta(days=30 + k * 45)
        face = rnd.choice([500_000, 750_000, 1_000_000, 1_500_000])
        y = round(rnd.uniform(3.8, 4.5), 2)
        db.session.add(TreasuryHolding(description=f"US T-Bill {mat:%m/%d/%y}", cusip=f"912797{rnd.randint(100, 999)}{rnd.choice('ABCDEFGH')}{rnd.randint(1, 9)}",
                                       bank_account=banks[3], face=face, cost=round(face * (1 - y / 100 * (30 + k * 45) / 365), 2), yld=y, maturity=mat))
    for vendor, desc, total, alloc in [("Northbridge IT", "Managed IT & security", 6_480, "Alladin Holdings LLC:50; Alladin Real Estate LP:30; Alladin Ventures LLC:20"),
                                       ("Raleigh office lease", "Office rent", 24_500, "Alladin Holdings LLC:60; Alladin Real Estate LP:25; Alladin Foundation:15"),
                                       ("Ridgeway CPA Group", "Audit & tax", 41_000, "Alladin Family Trust:40; Alladin Holdings LLC:30; Alladin Real Estate LP:30"),
                                       ("Chubb Personal Risk", "Umbrella policy", 96_000, "Tirumala:50; Alladin Holdings LLC:50"),
                                       ("Gusto", "Office payroll", 86_000, "Alladin Holdings LLC:70; Alladin Real Estate LP:20; Alladin Foundation:10"),
                                       ("Hale & Whitlock LLP", "Estate planning", 22_850, "Alladin Family Trust:70; Kaveri Alladin 2019 Trust:30")]:
        for m in range(2):
            db.session.add(SharedExpense(day=today - timedelta(days=30 * m + rnd.randint(1, 10)), vendor=vendor, description=desc, total=total, allocation=alloc, settled=m > 0))
    period_prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    period_prev2 = ((today.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    for per in (period_prev2, period_prev):
        for area, task, owner in [("Cash", "Bank reconciliations — all operating accounts", "Noah"), ("Cash", "Treasury bill accruals", "Noah"),
                                  ("Investments", "Record capital calls and distributions", "Elena"), ("Investments", "Update private marks from GP statements", "Sofia"),
                                  ("Real estate", "Post property-level P&Ls", "Elena"), ("Real estate", "DSCR covenant tests", "Elena"),
                                  ("Payables", "Accrue unpaid invoices", "Noah"), ("Intercompany", "Interest accruals on intercompany notes", "Noah"),
                                  ("Reporting", "Family net worth statement", "Priya"), ("Reporting", "Quarterly investment memo", "Marcus")]:
            done = per == period_prev2 or rnd.random() < .45
            db.session.add(CloseTask(period=per, area=area, task=task, owner=owner, due=today - timedelta(days=rnd.randint(-8, 20)),
                                     status="Complete" if done else rnd.choice(["Not started", "In progress"])))
        for ba in banks:
            book = ba.balance
            stmt = book if rnd.random() < .7 else round(book + rnd.uniform(-9000, 9000), 2)
            db.session.add(CloseTask(period=per, area="Bank rec", task=f"Reconcile {ba.name}", owner="Noah", bank_account=ba, book_balance=book,
                                     statement_balance=stmt, status="Complete" if (per == period_prev2 or book == stmt) else "In progress"))

    # ---------- operations / legal / reports / tax
    for carrier, kind, insured, cov, prem, rd in [("Chubb", "Umbrella liability", "Alladin family", 50_000_000, 96_000, 70), ("PURE", "Homeowners — primary residence", "Tirumala", 8_500_000, 31_200, 140),
                                                  ("AIG Private Client", "Fine art", "Alladin Holdings LLC", 4_500_000, 12_400, 220), ("Travelers", "Property — Cedar Bluff", "Cedar Bluff SPV", 42_000_000, 118_000, 45),
                                                  ("Hiscox", "D&O / fiduciary", "Alladin Holdings LLC", 10_000_000, 24_800, 190), ("Global Aerospace", "Aviation hull & liability", "Alladin Aviation LLC", 25_000_000, 41_000, 12),
                                                  ("Coalition", "Cyber", "Alladin Holdings LLC", 5_000_000, 9_600, 300), ("Zurich", "Property — Ironwood", "Ironwood SPV", 45_000_000, 96_500, 95)]:
        db.session.add(InsurancePolicy(carrier=carrier, kind=kind, insured=insured, coverage=cov, premium=prem, renews=today + timedelta(days=rd), broker="Marsh Private Client"))
    for name, cat, contact, spend, w9 in [("Ridgeway CPA Group", "Tax & audit", "Dana Ruiz", 164_000, True), ("Hale & Whitlock LLP", "Legal", "M. Whitlock", 212_000, True),
                                          ("Northbridge IT", "Technology", "Sam Ortega", 77_760, True), ("Cardinal Property Mgmt", "Property management", "J. Pruitt", 219_600, True),
                                          ("Marsh Private Client", "Insurance broker", "K. Ames", 0, True), ("Altitude Jet Services", "Aviation", "Ops desk", 442_800, False),
                                          ("Oakline Landscaping", "Household", "T. Greer", 31_800, False), ("Sterling Security", "Household", "Dispatch", 58_800, True),
                                          ("Iron Mountain", "Records", "Account team", 10_080, True), ("Gusto", "Payroll", "Support", 2_400, True)]:
        db.session.add(Vendor(name=name, category=cat, contact=contact, email=f"{contact.split()[0].lower()}@{name.split()[0].lower()}.example", annual_spend=spend, w9_on_file=w9))
    for name, kind, loc, owner, val in [("Primary residence — Raleigh", "Residence", "Raleigh, NC", "Tirumala", 7_900_000), ("Lake house — Lake Norman", "Residence", "Cornelius, NC", "Alladin Family Trust", 3_400_000),
                                        ("Contemporary art collection (14 works)", "Art", "Raleigh residence", "Alladin Holdings LLC", 4_200_000), ("1967 Porsche 911S", "Vehicle", "Raleigh garage", "Tirumala", 310_000),
                                        ("Jewelry", "Jewelry", "Bank vault", "Tirumala", 640_000), ("Wine cellar", "Collectibles", "Raleigh residence", "Tirumala", 220_000)]:
        db.session.add(PersonalAsset(name=name, kind=kind, location=loc, owner=owner, value=val, appraised=today - timedelta(days=rnd.randint(60, 900))))
    for title, cp, kind, ent, years, val, ar in [("Office lease — Raleigh", "Glenwood Office Partners", "Lease", "Alladin Holdings LLC", 5, 294_000, False),
                                                 ("Managed IT services agreement", "Northbridge IT", "Services", "Alladin Holdings LLC", 2, 77_760, True),
                                                 ("Property management — Cedar Bluff", "Cardinal Property Mgmt", "Services", "Alladin Real Estate LP", 3, 132_000, True),
                                                 ("Aircraft management agreement", "Altitude Jet Services", "Services", "Alladin Aviation LLC", 3, 372_000, True),
                                                 ("Engagement letter — tax & audit", "Ridgeway CPA Group", "Engagement", "Alladin Holdings LLC", 1, 164_000, True),
                                                 ("Side letter — Summit Arch III", "Summit Arch Capital", "Side letter", "Alladin Growth Trust", 10, 0, False),
                                                 ("Subscription agreement — Granite Peak", "Granite Peak Secondaries", "Subscription", "Alladin Growth Trust", 10, 5_500_000, False),
                                                 ("NDA — Project Harbor", "Lantern Peak Partners", "NDA", "Alladin Holdings LLC", 2, 0, False)]:
        start = today - timedelta(days=rnd.randint(30, 900))
        db.session.add(Contract(title=title, counterparty=cp, kind=kind, entity=ents[ent], start=start, end=start + timedelta(days=365 * years), value=val, auto_renew=ar))
    for title, kind, ent, counsel in [("Alladin Family Trust agreement (restated)", "Trust agreement", "Alladin Family Trust", "Hale & Whitlock LLP"),
                                      ("Holdings LLC operating agreement", "Operating agreement", "Alladin Holdings LLC", "Hale & Whitlock LLP"),
                                      ("Real Estate LP partnership agreement", "LP agreement", "Alladin Real Estate LP", "Hale & Whitlock LLP"),
                                      ("Kaveri Alladin 2019 Trust", "Trust agreement", "Kaveri Alladin 2019 Trust", "Hale & Whitlock LLP"),
                                      ("Foundation bylaws", "Bylaws", "Alladin Foundation", "Brennan Nonprofit Law"),
                                      ("Last will and testament — Tirumala", "Will", "Tirumala", "Hale & Whitlock LLP"),
                                      ("Durable power of attorney", "POA", "Tirumala", "Hale & Whitlock LLP"),
                                      ("Healthcare directive", "Directive", "Tirumala", "Hale & Whitlock LLP"),
                                      ("Ventures LLC operating agreement", "Operating agreement", "Alladin Ventures LLC", "Hale & Whitlock LLP"),
                                      ("Aviation LLC operating agreement", "Operating agreement", "Alladin Aviation LLC", "Hale & Whitlock LLP")]:
        ex = today - timedelta(days=rnd.randint(200, 3000))
        db.session.add(LegalDocument(title=title, kind=kind, entity=ents[ent], executed=ex, counsel=counsel, location="Vault + /Legal/Entity Docs",
                                     next_review=today + timedelta(days=rnd.randint(-30, 500))))
    db.session.add_all([
        LegalMatter(title="Magnolia Commons — tenant default (anchor)", kind="Litigation", counsel="Hale & Whitlock LLP", opened=today - timedelta(days=120), exposure=1_400_000, budget=150_000, spent=62_000, next_step="Mediation scheduled"),
        LegalMatter(title="Oakmont Village — zoning variance", kind="Regulatory", counsel="Brennan Land Use", opened=today - timedelta(days=60), exposure=0, budget=40_000, spent=11_500, next_step="Planning board hearing"),
        LegalMatter(title="Brightline seller note — payment delay", kind="Collections", counsel="Hale & Whitlock LLP", opened=today - timedelta(days=35), exposure=900_000, budget=35_000, spent=4_200, next_step="Forbearance term sheet", status="Open"),
        LegalMatter(title="Estate plan refresh", kind="Planning", counsel="Hale & Whitlock LLP", opened=today - timedelta(days=210), exposure=0, budget=60_000, spent=48_000, next_step="Sign restated trust", status="Open"),
        LegalMatter(title="Bayview lease dispute", kind="Litigation", counsel="Tampa Commercial Law", opened=today - timedelta(days=420), exposure=220_000, budget=50_000, spent=50_000, next_step="Settled", status="Closed"),
    ])
    for rep, per, summ in [("Family net worth statement", "Q3", "Net worth up 3.1% QoQ; private marks drove most of the gain."), ("Quarterly investment memo", "Q3", "Public book outperformed S&P by 1.2 pts; two PE marks down."),
                           ("Cash & liquidity report", "Oct", "18 months of runway at current burn; $2.1M of calls due within 60 days."), ("Real estate quarterly", "Q3", "Portfolio DSCR 1.62x; one asset below covenant watch."),
                           ("Capital account statements", "Q3", "Statements issued to 6 co-investors."), ("Family net worth statement", "Q2", "Net worth flat; public equities offset private markdowns.")]:
        db.session.add(ReportRun(report=rep, period=f"{per} {today.year}", generated_by=users["priya"], recipients="tirumala@alladin-fo.example", summary=summ, status="Sent"))
    yr = today.year - 1
    for ent, form in [("Alladin Family Trust", "1041"), ("Alladin Growth Trust", "1041"), ("Kaveri Alladin 2019 Trust", "1041"), ("Alladin Holdings LLC", "1065"),
                      ("Alladin Real Estate LP", "1065"), ("Alladin Ventures LLC", "1065"), ("Alladin Credit Partners LP", "1065"), ("Alladin Aviation LLC", "1065"),
                      ("Alladin Foundation", "990-PF"), ("Tirumala", "1040")]:
        due = date(yr + 1, 4 if form in ("1040", "1041") else 3, 15)
        ext = date(yr + 1, 10 if form in ("1040",) else 9, 15) if rnd.random() < .7 else None
        db.session.add(TaxFiling(entity=ents[ent], form=form, year=yr, due=due, extended_to=ext, preparer="Ridgeway CPA Group",
                                 status=rnd.choice(["Filed", "Filed", "Filed", "In progress"])))
        db.session.add(TaxFiling(entity=ents[ent], form=form, year=yr + 1, due=date(yr + 2, due.month, 15), preparer="Ridgeway CPA Group", status="Not started"))
    for i in Investment.query.filter(Investment.asset_class.in_(["Private Equity", "Venture Capital", "Real Estate", "Private Credit"]), Investment.status == "Active").all():
        exp = date(yr + 1, rnd.choice([3, 4, 5, 6, 8, 9]), 15)
        rec = exp - timedelta(days=rnd.randint(-40, 30)) if rnd.random() < .7 else None
        db.session.add(K1(investment=i, year=yr, expected=exp, received=rec if rec and rec <= today else None, estimate=rnd.random() < .15))
    for ent in ("Tirumala", "Alladin Family Trust"):
        for q, (m, d) in enumerate([(4, 15), (6, 15), (9, 15), (1, 15)]):
            y = today.year if q < 3 else today.year + 1
            due = date(y, m, d)
            for jur in ("Federal", "NC"):
                db.session.add(EstimatedTax(entity=ents[ent], jurisdiction=jur, quarter=f"Q{q + 1}", due=due, amount=rnd.choice([180_000, 240_000, 310_000]) if jur == "Federal" else rnd.choice([22_000, 31_000]),
                                            paid_on=due - timedelta(days=3) if due < today else None))
    for ent, item, auth, dd in [("Alladin Holdings LLC", "Delaware annual franchise tax", "Delaware", 120), ("Alladin Real Estate LP", "Delaware annual tax", "Delaware", 120),
                                ("Alladin Ventures LLC", "Delaware annual franchise tax", "Delaware", 120), ("Alladin Holdings LLC", "NC foreign LLC annual report", "North Carolina", 150),
                                ("Alladin Foundation", "NC charitable solicitation renewal", "North Carolina", 40), ("Alladin Holdings LLC", "Beneficial ownership (BOI) update", "FinCEN", -10),
                                ("Alladin Real Estate LP", "Texas franchise tax report", "Texas", 180), ("Alladin Aviation LLC", "FAA registration renewal", "FAA", 300),
                                ("Alladin Credit Partners LP", "Form D amendment", "SEC", 60), ("Alladin Family Trust", "Trustee certification", "Trustee", 25)]:
        db.session.add(ComplianceItem(entity=ents[ent], item=item, authority=auth, due=today + timedelta(days=dd), status="Overdue" if dd < 0 else "Pending"))

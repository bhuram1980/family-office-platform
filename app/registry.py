"""App registry: names, colours and sidebar navigation for the ten apps."""

APPS = {}


def app(id, name, short, sub, color, desc, dark=False, fill=False, nav=None):
    APPS[id] = dict(id=id, name=name, short=short, sub=sub, color=color, desc=desc,
                    dark=dark, fill=fill, nav=nav or [])


def item(label, ep, icon="circle", sub=False, badge=None, **args):
    return dict(label=label, ep=ep, icon=icon, sub=sub, badge=badge, args=args)


def section(title, items, collapsible=False):
    return dict(title=title, items=items, collapsible=collapsible)


app("stocks", "Stocks", "ST", "Stocks", "#0f172a",
    "Portfolio manager for a multi-account public equity book: positions, tax lots, trades, options, exposure and research.",
    nav=[
        section("Portfolio", [
            item("Dashboard", "stocks.dashboard", "layout-dashboard"),
            item("Daily Review", "stocks.daily_review", "clipboard-check"),
            item("Holdings", "stocks.holdings", "briefcase"),
            item("Month-End", "stocks.month_end", "calendar-range", sub=True),
            item("Activity", "stocks.trade_log", "activity"),
            item("P&L", "stocks.pnl", "trending-up"),
            item("Fees", "stocks.fees", "receipt", sub=True),
            item("Short Options", "stocks.options", "sigma"),
            item("Dividends", "stocks.dividends", "coins"),
            item("Exposure", "stocks.exposure", "pie-chart"),
            item("Market", "stocks.market", "globe", sub=True),
            item("Categories", "stocks.categories", "layers"),
        ]),
        section("Research", [
            item("Review Board", "stocks.review", "kanban-square"),
            item("Themes", "stocks.themes", "sparkles"),
            item("Watchlist", "stocks.watchlist", "eye", badge="watch"),
            item("Trading", "stocks.actions", "arrow-left-right", badge="proposals"),
            item("Notes", "stocks.notes", "notebook-pen"),
            item("Comparison", "stocks.comparison", "git-compare"),
            item("Charts", "stocks.charts", "line-chart"),
        ]),
        section("System", [
            item("Securities", "stocks.securities_list", "database"),
            item("Accounts", "stocks.accounts_list", "landmark"),
            item("Settings", "stocks.settings", "settings"),
        ]),
    ])

app("family-office", "Family Office", "FO", "Family Office", "#0b1220",
    "The office's books: entities, investments, real estate, cash, loans, close and reporting in one ledger.", dark=True,
    nav=[
        section(None, [
            item("Data Map", "family_office.data_map", "network"),
            item("Dashboard", "family_office.dashboard", "layout-dashboard"),
            item("Financial Statement", "family_office.pfs", "file-text"),
        ]),
        section("Portfolio", [
            item("Investments", "family_office.investments_list", "briefcase"),
            item("Map View", "family_office.investment_map", sub=True),
            item("Entities & Org Chart", "family_office.entities", "network"),
            item("Asset Allocation", "family_office.allocation", "pie-chart"),
            item("Distributions", "family_office.distributions_list", "hand-coins"),
            item("Performance", "family_office.performance", "trending-up"),
            item("P&L by Entity", "family_office.pnl", "scale"),
            item("Valuation", "family_office.valuations_list", "badge-dollar-sign"),
            item("Portfolio Analytics", "family_office.analytics", "bar-chart-3"),
            item("Deal Parameters", "family_office.deal_parameters", "sliders-horizontal"),
            item("Sold Deals", "family_office.sold_deals", sub=True),
            item("Non-Marketable", "family_office.non_marketable", sub=True),
            item("Collections", "family_office.collections", sub=True),
            item("Loans", "family_office.loans_list", "landmark"),
            item("Intercompany", "family_office.intercompany", sub=True),
            item("Shared Expenses", "family_office.shared_expenses_list", sub=True),
            item("Transactions", "family_office.transactions_list", sub=True),
        ], collapsible=True),
        section("Real Estate", [
            item("RE Dashboard", "family_office.re_dashboard", "building-2"),
            item("Properties", "family_office.properties", "home"),
            item("RE Financials", "family_office.re_financials", "table"),
            item("Report Card", "family_office.report_card", "award"),
            item("Underwriting", "family_office.underwriting", "calculator"),
            item("Financials Review", "family_office.re_review", sub=True),
            item("Debt", "family_office.debt", "landmark"),
            item("1031 Exchanges", "family_office.exchanges_list", "repeat"),
        ], collapsible=True),
        section("Cash & Treasury", [
            item("Cash Hub", "family_office.cash_hub", "wallet"),
            item("Cash Accounts", "family_office.cash_list", sub=True),
            item("Cash Report", "family_office.cash_report", sub=True),
            item("Treasury", "family_office.treasury_list", sub=True),
            item("Cash Forecast", "family_office.cash_forecast", sub=True),
            item("Expected Cash", "family_office.expected_cash", sub=True),
            item("Cash Grid", "family_office.cash_grid", sub=True),
            item("Recurring Cash", "family_office.recurring_cash_list", sub=True),
            item("Family Obligations", "family_office.family_obligations_list", sub=True),
            item("Brokerage", "family_office.brokerage", sub=True),
            item("Cash-flow Recon", "family_office.cashflow_recon", sub=True),
            item("Wire Forms", "family_office.wire_forms_list", sub=True),
        ], collapsible=True),
        section("Accounting & Close", [
            item("Close", "family_office.close", "check-square"),
            item("Bank Recon", "family_office.close_recon", sub=True),
        ], collapsible=True),
        section("Operations", [
            item("Bills & Payables", "family_office.bills_list", "receipt"),
            item("Insurance", "family_office.insurance_list", "shield"),
            item("Vendors", "family_office.vendors_list", "store"),
            item("Personal Assets", "family_office.personal_assets_list", "gem"),
        ], collapsible=True),
        section("Legal", [
            item("Entity Documents", "family_office.legal_docs_list", "file-badge"),
            item("Contracts", "family_office.contracts_list", "file-signature"),
            item("Matters", "family_office.matters_list", "gavel"),
        ], collapsible=True),
        section("Reports", [
            item("Report Library", "family_office.reports", "library"),
            item("Net Worth Report", "family_office.report_net_worth", sub=True),
            item("Capital Accounts", "family_office.report_capital_accounts", sub=True),
            item("Quarterly Summary", "family_office.report_quarterly", sub=True),
        ], collapsible=True),
        section("Tax & Admin", [
            item("Tax Filings", "family_office.tax_filings_list", "file-check"),
            item("K-1 Tracker", "family_office.k1s_list", "inbox"),
            item("Estimated Taxes", "family_office.estimated_tax_list", "calendar-clock"),
            item("Compliance Calendar", "family_office.compliance_list", "calendar-check"),
        ], collapsible=True),
    ])
app("deals", "Deal Evaluator", "DE", "Deal Evaluator", "#4f46e5",
    "Screen, score and track every deal from first look to sign-off, with follow-ups and a full audit trail.")
app("pevc", "PE / VC", "PV", "PE / VC Monitor", "#059669",
    "Private-markets monitor: commitments, calls, NAV, TVPI and the documents behind every mark.")
app("documents", "Documents", "DC", "Documents", "#4f46e5",
    "An inbox that reads statements and notices, proposes where each file belongs, and files it on approval.")
app("philanthropy", "Philanthropy", "PH", "Philanthropy", "#e11d48",
    "Family giving: grants, approvals, recipients, fund balance and reconciliation against the donor-advised fund.")
app("tasks", "Tasks", "TK", "Tasks", "#2563eb",
    "The office's work queue: assignments, sign-offs, recurring checklists, projects and meetings.")
app("real-estate", "Real Estate", "RE", "Real Estate", "#16a34a",
    "Property portfolio: value, equity, NOI, debt, DSCR and a market watch for every metro you own in.",
    nav=[
        section("Portfolio", [
            item("Dashboard", "real_estate.dashboard", "layout-dashboard"),
            item("Properties", "real_estate.properties", "building-2"),
            item("Issue Queue", "real_estate.issues", "triangle-alert", badge="re_issues"),
            item("Debt", "real_estate.debt", "landmark"),
            item("Markets", "real_estate.markets", "map"),
            item("Portfolio Q&A", "real_estate.ai", "sparkles"),
        ]),
        section("System", [
            item("Settings", "real_estate.settings", "settings"),
        ]),
    ])
app("ir-portal", "IR Portal", "IR", "Investor Portal", "#2563eb",
    "What co-investors see: their entities, positions, documents, capital calls and messages.", fill=True)
app("admin", "Admin", "AD", "Admin", "#0f172a",
    "Platform administration: users, access, sign-in activity, API spend, credentials, audit and health.", fill=True,
    nav=[
        section("Workspace", [
            item("Dashboard", "admin.dashboard", "layout-dashboard"),
            item("Users", "admin.users", "users"),
            item("Announcements", "admin.announcements_list", "megaphone"),
        ]),
        section("Platform", [
            item("Activity", "admin.activity", "activity"),
            item("API usage", "admin.usage", "gauge"),
            item("Credentials", "admin.credentials_list", "key-round"),
            item("Settings", "admin.settings", "settings"),
            item("Audit log", "admin.audit", "scroll-text"),
            item("Email log", "admin.email_log", "mail"),
            item("System & health", "admin.system", "server"),
        ]),
        section("Account", [
            item("My profile", "admin.profile", "user"),
            item("Notifications", "admin.notifications", "bell"),
            item("Passkeys", "admin.passkeys", "fingerprint"),
        ]),
    ])

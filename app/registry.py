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
    "The office's books: entities, investments, real estate, cash, loans, close and reporting in one ledger.", dark=True)
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
    "Property portfolio: value, equity, NOI, debt, DSCR and a market watch for every metro you own in.")
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

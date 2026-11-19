# Bhuram Family Office platform

Ten connected apps for running a family office, built as one Flask application on one PostgreSQL database with a single sign-on:

| App | Path | What works |
|---|---|---|
| Stocks | `/stocks/` | Multi-account equity book: positions from tax lots, FIFO trades, trade proposals → admin approval → booking, options, dividends, exposure, P&L, research board, watchlist |
| Family Office | `/family-office/` | Entities and org chart, investments, distributions, valuations, P&L, allocation, cash hub and forecast, wires with a two-person rule, bills, insurance, loans, month-end close checklist, legal, tax (K-1s, estimates), net-worth and capital-account reports |
| Deal Evaluator | `/deals/` | Drag-and-drop pipeline and table, weighted scoring with editable weights, IC score gate, admin-only approve/pass, follow-ups, notes, side-by-side compare, convert an approved deal into a Family Office investment |
| PE / VC | `/pevc/` | Commitments, calls, NAV, TVPI/DPI, J-curve, attention queue, portfolio-company operating metrics, GP updates inbox, document coverage by quarter |
| Documents | `/documents/` | Upload/inbox, rules-based classifier, PDF preview, file-to-ledger (creates capital calls, distributions, PE/VC documents), approve/reject/flag, soft delete and recovery, Dropbox-style sync, document request tracker, e-signatures with signing order, audit |
| Philanthropy | `/philanthropy/` | Grant requests, approvals (two admins above a threshold), payment from the DAF (ledger) or the Foundation (posts to Family Office cash), recipients directory, tuition, budgets by cause, reconciliation |
| Tasks | `/tasks/` | Drag-and-drop Kanban with an admin-only sign-off column, comments, projects, recurring tasks that spawn on schedule, meetings with action items, deleted-task recovery |
| Real Estate | `/real-estate/` | Properties with monthly operating data, NOI, DSCR, debt and rate-shock analysis, review workflow, rules engine that raises an issue queue, market watch map, rule-based Q&A |
| IR Portal | `/ir-portal/` | Co-investor portal: holdings and NAV by investing profile, value history, properties owned, offerings with indicate/commit/withdraw, documents (marked viewed on download), messaging with the office, sign-in history. Staff can view as any investor, answer messages and manage offerings. Investors only ever see their own data |
| Admin | `/admin/` | Users, roles, app access, unlock accounts, announcements, sign-in activity, API spend, credentials hints, audit log, settings, health |

The apps share one database, so work done in one shows up in the others: an approved deal becomes a Family Office investment, a filed capital-call notice becomes a capital call, a Foundation grant payment is a cash transaction, Real Estate and Family Office share the same properties and loans, and IR Portal positions are valued from Family Office marks.

Stack: Python 3.12+, Flask, SQLAlchemy 2, Flask-Migrate (Alembic), Flask-Login, PostgreSQL 16, Jinja templates with HTMX for in-place updates, Chart.js, gunicorn.

**All seeded data is synthetic.** Every company figure, entity, person and amount is invented.

## Run it locally with Docker

```bash
docker compose up --build -d
docker compose exec web flask seed      # load the synthetic data set
open http://localhost:8000
```

## Run it locally without Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
createdb fo                              # any Postgres 14+
export DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/fo
export FLASK_APP=app:create_app
flask db upgrade
flask seed
flask run                                 # http://127.0.0.1:5000
```

## Seeded accounts

Locally, all seeded users share the password `bhuram-demo`. **Never expose that publicly**: `flask rotate-passwords --out FILE` gives every user a random password (written to FILE with mode 600, never printed). The public deployment uses rotated passwords.

| Username | Role | Access |
|---|---|---|
| `tirumala` | Super admin | everything |
| `priya` | Admin | everything; can approve trades and manage users |
| `marcus` | Analyst | Stocks, PE/VC, Deals, Tasks, Documents |
| `elena` | Analyst | Family Office, Real Estate, Documents, Tasks, Philanthropy, PE/VC |
| `sofia`, `noah` | Analyst | subsets |
| `devon` | Viewer | read-only Family Office and Documents |
| `leah`, `omar` | Investor | IR Portal only |

Roles: **super admin** (all apps, can create other super admins), **admin** (user management, approvals), **analyst** (read/write in granted apps), **viewer** (read-only), **investor** (IR Portal only). Five failed sign-ins lock an account; admins unlock it from Admin → Users.

## Screenshots

`screenshots/` holds the landing page (`landing.png`, `landing_full.png`) and each app dashboard as `tirumala`, plus the IR Portal as investor `leah` (`ir-portal_as_investor_leah.png`) and in office view (`ir-portal_office_view.png`).

## Commands

| Command | Does |
|---|---|
| `flask seed` | Drop and recreate all tables, load synthetic data, stamp the migration head |
| `flask refresh-prices` | One simulated market tick (swap `services/portfolio.refresh_prices` for a real feed) |
| `flask create-user USERNAME "Full Name" --role admin` | Add a user from the shell |
| `flask db migrate -m "..."` / `flask db upgrade` | Schema migrations |
| `pytest` | Test suite (needs a `fo_test` database or `TEST_DATABASE_URL`) |

## Deploying

GitHub Pages only serves static files, so it cannot run this app. Any host that runs a Python web process next to Postgres works.

**Vercel** (how the live copy runs): the repo deploys as a Python (Flask) project with zero config. `wsgi.py` is the entrypoint, static files are served from `public/static` by the CDN, and `vercel.json` sets the function duration.
1. Import the repo as a Vercel project and add a Postgres database (Neon from the Vercel Marketplace, or any Postgres). Use the pooled connection string as `DATABASE_URL`.
2. Set `SECRET_KEY` to a long random string (the app refuses to start on Vercel without one).
3. Vercel functions cannot run shell commands, so bootstrap the database once through a token-guarded endpoint: set `SETUP_TOKEN` (32+ random characters), redeploy, then
   `curl -X POST https://<host>/_setup -H "Authorization: Bearer $SETUP_TOKEN" -H "Content-Type: application/json" -d '{"seed": true, "passwords": {"tirumala": "<new strong password>"}}'`.
   It runs the migrations, loads the synthetic data and sets the given passwords. Then delete `SETUP_TOKEN` and redeploy; the route disappears.
   If you can reach the database from your machine, `flask db upgrade && flask seed && flask rotate-passwords --out creds.txt` does the same.
4. Uploads are capped at 4 MB on Vercel (the platform limit is 4.5 MB per request).

**Render**: create a PostgreSQL instance, then a Web Service from this repo with
- Build command: `pip install -r requirements.txt`
- Start command: `flask db upgrade && gunicorn -w 3 -b 0.0.0.0:$PORT wsgi:app`
- Environment: `DATABASE_URL` (Render's internal URL works; `postgres://` is rewritten automatically), `SECRET_KEY`, `FLASK_APP=app:create_app`
- Seed once from the Render shell: `flask seed`

**Fly.io**: `fly launch` (uses the Dockerfile), `fly postgres create` and `fly postgres attach`, `fly secrets set SECRET_KEY=...`, `fly deploy`, then `fly ssh console -C "flask seed"`.

The container's start command runs `flask db upgrade` before gunicorn, so new migrations apply on every deploy.

## Layout

```
app/
  __init__.py        app factory, CSRF, error pages, Jinja globals
  registry.py        the ten apps: names, colours, sidebar navigation
  crud.py            declarative list/create/edit/delete/CSV for any model
  models/            one SQLAlchemy module per app, all in one database
  blueprints/        one blueprint per app
  services/          portfolio maths, audit logging, app logic
  seed/              synthetic data, one module per app
  templates/         shared shell (base.html), macros, per-app pages
  static/            CSS, JS (charts, tabs, sorting, toasts), previews
migrations/          Alembic
tests/               pytest: auth, permissions, every page renders, write paths
```

## Security notes

- Passwords are hashed with Werkzeug (scrypt). Sessions are HTTP-only, SameSite=Lax cookies.
- Every POST requires a per-session CSRF token (forms and HTMX).
- Each app checks sign-in and per-user app access before every request; writes check role.
- Every create, update, delete, approval, trade and sign-in is written to the audit log (Admin → Audit log).
- Credentials in Admin store only a key hint; real secrets belong in environment variables.

## Continuous integration

The GitHub Actions workflow lives at `ci/github-actions-ci.yml`. It runs migrations against a fresh Postgres 16 service, checks that migrations match the models, runs the test suite and the seed script. To switch it on, move it to `.github/workflows/ci.yml` (the token used to push this repo did not have the `workflow` scope, so it could not be committed there directly):

```bash
mkdir -p .github/workflows && git mv ci/github-actions-ci.yml .github/workflows/ci.yml && git commit -m "Enable CI" && git push
```

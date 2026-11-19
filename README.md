# Bhuram Family Office platform

Ten connected apps for running a family office, built as one Flask application on one PostgreSQL database with a single sign-on:

| App | Path | What it does |
|---|---|---|
| Stocks | `/stocks/` | Multi-account equity book: positions from tax lots, FIFO trades, proposals → approval → booking, options, dividends, exposure, research board |
| Family Office | `/family-office/` | Entities, investments, distributions, real estate, cash & treasury, loans, close, legal, reports, tax |
| Deal Evaluator | `/deals/` | Pipeline board and table, scoring, follow-ups, sign-offs, deal pages |
| PE / VC | `/pevc/` | Commitments, calls, NAV, TVPI, attention queue, portfolio-company financials |
| Documents | `/documents/` | Inbox review queue, classification, filing, e-signatures, coverage |
| Philanthropy | `/philanthropy/` | Grants, approvals, recipients, reconciliation, ledger |
| Tasks | `/tasks/` | Kanban with sign-off columns, projects, recurring tasks, meetings |
| Real Estate | `/real-estate/` | Properties, NOI, debt, DSCR, market watch, issue queue |
| IR Portal | `/ir-portal/` | Co-investor view of entities, positions, documents, messages |
| Admin | `/admin/` | Users, roles, app access, sign-in activity, API spend, audit, settings, health |

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

All seeded users share the password `bhuram-demo`. **Change these before exposing the app anywhere.**

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

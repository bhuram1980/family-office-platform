from datetime import datetime, timedelta, date

from ..extensions import db
from ..models import (User, LoginEvent, AuditLog, Announcement, Notification, ApiCredential,
                       ApiUsage, Setting, EmailLog, Passkey, APP_IDS)

PASSWORD = "alladin-demo"

USERS = [
    # username, name, role, title, color, apps
    ("tirumala", "Tirumala", "super_admin", "Principal", "#4f46e5", None),
    ("priya", "Priya Raman", "admin", "Chief Financial Officer", "#0ea5e9", None),
    ("marcus", "Marcus Oyelaran", "analyst", "Portfolio Manager", "#f59e0b", "stocks,pevc,deals,tasks,documents"),
    ("elena", "Elena Vasquez", "analyst", "Controller", "#10b981", "family-office,real-estate,documents,tasks,philanthropy,pevc"),
    ("sofia", "Sofia Lindqvist", "analyst", "Investment Associate", "#ec4899", "deals,pevc,real-estate,tasks,documents"),
    ("noah", "Noah Achterberg", "analyst", "Staff Accountant", "#8b5cf6", "family-office,documents,tasks,philanthropy"),
    ("devon", "Devon Park", "viewer", "Outside Auditor", "#64748b", "family-office,documents"),
    ("leah", "Leah Whitford", "investor", "Co-investor", "#2563eb", "ir-portal"),
    ("omar", "Omar Haddad", "investor", "Co-investor", "#0891b2", "ir-portal"),
]


def seed(ctx):
    rnd = ctx["rnd"]
    users = {}
    for un, name, role, title, color, apps in USERS:
        u = User(username=un, name=name, email=f"{un}@alladin-fo.example", role=role, title=title, color=color,
                 app_access=apps or ",".join(APP_IDS))
        u.set_password(PASSWORD)
        db.session.add(u)
        users[un] = u
    db.session.flush()
    ctx["users"] = users
    staff = [u for u in users.values() if u.role != "investor"]

    now = datetime.utcnow()
    for d in range(30):
        day = now - timedelta(days=d)
        for u in staff:
            if day.weekday() >= 5 and rnd.random() < .7:
                continue
            for _ in range(rnd.choice([0, 1, 1, 2])):
                hr = rnd.choice([7, 8, 8, 9, 9, 10, 13, 14, 16, 20])
                db.session.add(LoginEvent(user_id=u.id, username=u.username, success=True, ip=f"10.20.{rnd.randint(1,9)}.{rnd.randint(2,250)}",
                                          user_agent="Mozilla/5.0", at=day.replace(hour=hr, minute=rnd.randint(0, 59))))
        if rnd.random() < .25:
            db.session.add(LoginEvent(username=rnd.choice(["admin", "root", "priya", "test"]), success=False,
                                      ip=f"185.{rnd.randint(10,200)}.{rnd.randint(1,250)}.{rnd.randint(1,250)}", at=day.replace(hour=rnd.randint(0, 23))))
        for _ in range(rnd.randint(3, 9)):
            u = rnd.choice(staff)
            app, action, ent = rnd.choice([("stocks", "update", "stk_securities"), ("family-office", "create", "fo_cash_txns"),
                                          ("documents", "file", "doc_attachments"), ("tasks", "update", "tasks"),
                                          ("deals", "update", "deals"), ("admin", "update", "users"), ("real-estate", "update", "re_properties")])
            db.session.add(AuditLog(user_id=u.id, app=app, action=action, entity=ent, entity_id=rnd.randint(1, 60),
                                    detail=f"{action.title()} {ent.split('_')[-1].rstrip('s')} #{rnd.randint(1,60)}",
                                    at=day.replace(hour=rnd.randint(7, 19), minute=rnd.randint(0, 59))))

    db.session.add_all([
        Announcement(title="Q4 close calendar is posted", body="Bank recs due the 5th business day; investment marks by the 12th.", level="info", active=True, author=users["priya"]),
        Announcement(title="Custodian maintenance Saturday", body="Statement downloads paused 02:00–06:00 ET.", level="warning", active=False, author=users["tirumala"]),
        Announcement(title="New: passkey sign-in", body="Register a passkey from My profile → Passkeys.", level="info", active=False, author=users["tirumala"]),
    ])
    for u in staff:
        for t, l in [("Two trade proposals need your decision", "/stocks/actions/"), ("Close checklist: 4 items due this week", "/tasks/"),
                     ("New capital call notice filed", "/documents/")]:
            db.session.add(Notification(user_id=u.id, title=t, link=l, read=rnd.random() < .4, at=now - timedelta(hours=rnd.randint(1, 120))))
    for prov, label, hint, scope, exp in [
        ("Market data", "Equity prices (delayed)", "…4f2a", "quotes:read", date(2027, 3, 31)),
        ("Custodian SFTP", "Statement pickup", "…91c0", "sftp:read", date(2027, 1, 15)),
        ("Bank API", "Operating accounts", "…7d13", "balances:read transactions:read", date(2026, 12, 20)),
        ("Email (IMAP)", "documents@ inbox", "…e5b8", "mail:read", None),
        ("LLM provider", "Classification & scoring", "…0a77", "inference", None),
        ("E-signature", "Envelope status", "…c3d9", "envelopes:read", date(2027, 6, 30)),
    ]:
        db.session.add(ApiCredential(provider=prov, label=label, key_hint=hint, scope=scope, expires_on=exp, active=True))
    for d in range(30):
        day = date.today() - timedelta(days=d)
        for prov, app, base in [("LLM provider", "documents", 1.6), ("LLM provider", "deals", .7), ("Market data", "stocks", .25), ("Bank API", "family-office", .1)]:
            calls = int(rnd.uniform(.4, 1.6) * base * 220)
            db.session.add(ApiUsage(day=day, provider=prov, app=app, calls=calls, cost=round(calls * base * rnd.uniform(.004, .006), 2)))
    for k, v, l in [("org_name", "Alladin Family Office", "Organisation name"), ("session_hours", "12", "Session length (hours)"),
                    ("lockout_attempts", "5", "Failed sign-ins before lockout"), ("fiscal_year_start", "01-01", "Fiscal year start (MM-DD)"),
                    ("base_currency", "USD", "Base currency"), ("require_passkey_admins", "false", "Require passkeys for admins"),
                    ("backup_time", "02:30", "Nightly backup (UTC)")]:
        db.session.add(Setting(scope="platform", key=k, value=v, label=l))
    kinds = [("daily-review", "Daily portfolio review"), ("digest", "Weekly task digest"), ("reset", "Password reset"), ("alert", "Bill due alert")]
    for i in range(48):
        k, subj = rnd.choice(kinds)
        u = rnd.choice(staff)
        db.session.add(EmailLog(to_addr=u.email, subject=subj, kind=k, status="failed" if rnd.random() < .05 else "sent",
                                at=now - timedelta(hours=i * 13 + rnd.randint(0, 6))))
    db.session.add_all([Passkey(user=users["tirumala"], name="MacBook Pro · Touch ID", last_used_at=now - timedelta(days=1)),
                        Passkey(user=users["tirumala"], name="iPhone 16", last_used_at=now - timedelta(days=6)),
                        Passkey(user=users["priya"], name="YubiKey 5C", last_used_at=now - timedelta(days=3))])

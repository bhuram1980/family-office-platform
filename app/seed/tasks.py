"""Synthetic tasks, projects, recurring checklists and meetings."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import Meeting, Project, RecurringTask, Task, TaskComment, User

PROJECTS = [("Year-end tax package", "#2563eb"), ("Q4 investment committee", "#7c3aed"), ("Ironwood refinance", "#16a34a"),
            ("Foundation grant cycle", "#e11d48"), ("Insurance renewal", "#f59e0b"), ("Systems clean-up", "#0891b2")]
TITLES = [
    ("Reconcile operating accounts for October", "family-office"), ("Book Q3 capital account statements", "pevc"), ("Send K-1 estimates to CPA", "family-office"),
    ("Review Cedar Bluff budget vs actual", "real-estate"), ("Draft IC memo for Harborline Logistics", "deals"), ("Collect W-9s from new vendors", "family-office"),
    ("Approve October grant disbursements", "philanthropy"), ("Update margin targets after rebalance", "stocks"), ("Renew umbrella liability policy", "family-office"),
    ("File 1031 identification notice", "family-office"), ("Chase missing Q3 statement from Tidewater", "pevc"), ("Prepare lender package for Ironwood", "real-estate"),
    ("Schedule annual trust review with counsel", "family-office"), ("Upload signed side letter", "documents"), ("Reconcile DAF balance", "philanthropy"),
    ("Review option expirations for next week", "stocks"), ("Investor letter for co-investors", "ir-portal"), ("Close September books — Holdings", "family-office"),
    ("Confirm wire instructions by phone", "family-office"), ("Run quarterly review for venture book", "pevc"), ("Tag inbox attachments from GP portals", "documents"),
    ("Property tax appeal — Riverbend", "real-estate"), ("Board deck for Northgate Software", "pevc"), ("Tuition payment for spring semester", "philanthropy"),
    ("Archive closed deals", "deals"), ("Refresh user access review", "admin"), ("Estimated tax payment Q4", "family-office"), ("Score three new inbound deals", "deals"),
    ("Update cash forecast for December", "family-office"), ("Review appraisal for Bayview Medical", "real-estate"), ("Reset passwords for departed contractor", "admin"),
    ("Clean up duplicate vendor records", "family-office"), ("Sign off on Q3 close", "family-office"), ("Review new co-investor subscription docs", "ir-portal"),
]
RECUR = [("Monthly bank reconciliations", "Monthly"), ("Weekly cash position email", "Weekly"), ("Quarterly GP statement chase", "Quarterly"),
         ("Monthly property P&L review", "Monthly"), ("Daily trade blotter check", "Daily"), ("Annual insurance schedule review", "Annual")]


def seed(ctx):
    rnd = ctx["rnd"]
    staff = User.query.filter(User.role.in_(["super_admin", "admin", "analyst"])).all()
    boss = User.query.filter_by(role="super_admin").first()
    today = date.today()
    projs = []
    for n, c in PROJECTS:
        p = Project(name=n, color=c, owner_id=rnd.choice(staff).id, due=today + timedelta(days=rnd.randint(10, 80)), description=f"{n} workstream.")
        db.session.add(p)
        projs.append(p)
    rec = []
    for t, f in RECUR:
        r = RecurringTask(title=t, frequency=f, next_due=today + timedelta(days=rnd.randint(1, 25)), assignee_id=rnd.choice(staff).id, priority="Normal")
        db.session.add(r)
        rec.append(r)
    meets = []
    for k, t in enumerate(["Weekly ops stand-up", "Investment committee", "Real estate asset review", "Foundation board", "Month-end close kickoff"]):
        m = Meeting(title=t, day=datetime.combine(today - timedelta(days=rnd.randint(1, 20)), datetime.min.time()) + timedelta(hours=10),
                    attendees=", ".join(u.first_name for u in rnd.sample(staff, 4)), agenda="1. Open items\n2. Decisions needed\n3. Next steps",
                    notes="Reviewed open items; owners confirmed dates for each action below.")
        db.session.add(m)
        meets.append(m)
    db.session.flush()
    weights = [10, 7, 4, 3, 2, 8, 1]
    from ..models.tasks import TASK_STATUSES
    for i, (t, app) in enumerate(TITLES):
        stt = rnd.choices(TASK_STATUSES, weights)[0]
        a = rnd.choice(staff)
        task = Task(title=t, app=app, status=stt, priority=rnd.choices(["Urgent", "High", "Normal", "Low"], [1, 3, 6, 2])[0], assignee_id=a.id,
                    reviewer_id=boss.id if stt == "Done – Waiting Sign Off" else rnd.choice(staff).id, created_by_id=rnd.choice(staff).id,
                    project_id=rnd.choice(projs).id if rnd.random() < 0.6 else None, meeting_id=rnd.choice(meets).id if rnd.random() < 0.25 else None,
                    due=today + timedelta(days=rnd.randint(-12, 30)), description=f"{t}. Attach support and move to review when finished.")
        if stt == "Done":
            task.completed_at = datetime.utcnow() - timedelta(days=rnd.randint(1, 30))
        if i % 17 == 16:
            task.deleted_at = datetime.utcnow() - timedelta(days=2)
        db.session.add(task)
        db.session.flush()
        for _ in range(rnd.randint(0, 3)):
            db.session.add(TaskComment(task_id=task.id, user_id=rnd.choice(staff).id, body=rnd.choice(
                ["Started on this.", "Waiting on the bank statement.", "Support attached.", "Can you take a look before Friday?", "Updated the numbers."])))

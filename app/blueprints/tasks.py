"""Tasks: kanban board, table, projects, recurring checklists, meetings, outstanding, trash and settings."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import Meeting, Project, RecurringTask, Task, TaskComment, User
from ..models.tasks import BOARD, PRIORITIES, TASK_STATUSES
from ..pages import D, b, card, chart, donut, form, html, kpis, link, lst, note, pill, render, row, status, table, tabs, bar_chart
from ..services import settings as st
from ..services.audit import audit
from .common import make_bp, write_required

bp = make_bp("tasks", "tasks")
APP_CHOICES = ["family-office", "stocks", "real-estate", "pevc", "deals", "documents", "philanthropy", "ir-portal", "admin"]
PRI_TONE = {"Urgent": "red", "High": "amber", "Normal": "blue", "Low": "gray"}
SETTINGS = [("signoff_required", "Tasks need a sign-off by an admin before Done", "yes", ["yes", "no"]),
            ("default_reviewer", "Default reviewer (username)", "tirumala"), ("wip_limit", "In-progress limit per person", "6", "number")]


def u(ep, **kw):
    return url_for(f"tasks.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return Markup(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                  f'<button class="{cls}">{escape(label)}</button></form>')


def staff():
    return User.query.filter(User.role.in_(["super_admin", "admin", "analyst"])).order_by(User.name).all()


def live():
    return Task.query.filter(Task.deleted_at.is_(None))


def _soft_delete(t):
    t.deleted_at = datetime.utcnow()


def _on_save(t, new):
    if new:
        t.created_by_id = current_user.id
        if not t.reviewer_id:
            rv = User.query.filter_by(username=st.get("tasks", "default_reviewer", "tirumala")).first()
            t.reviewer_id = rv.id if rv else None
    if t.status == "Done" and not t.completed_at:
        t.completed_at = datetime.utcnow()


Resource("tasks", "tasks", Task, "All Tasks", [
    F("title", required=True), F("status", type="select", choices=TASK_STATUSES, default="To Do"), F("priority", type="select", choices=PRIORITIES, default="Normal"),
    F("assignee_id", "Assignee", type="fk", fk=User, fk_label=lambda x: x.name), F("reviewer_id", "Reviewer", type="fk", fk=User, fk_label=lambda x: x.name, list=False),
    F("project_id", "Project", type="fk", fk=Project), F("app", "Related app", type="select", choices=APP_CHOICES), F("due", type="date"),
    F("meeting_id", "From meeting", type="fk", fk=Meeting, list=False), F("description", type="text", list=False),
], singular="Task", order_by=Task.due, filters=["status", "priority"], query=lambda: live(), nav="tasks.table_view",
    on_save=_on_save, on_delete=_soft_delete, after_save=lambda t: u("task", tid=t.id), row_link=lambda t: u("task", tid=t.id)).register(bp)

Resource("tasks", "projects", Project, "Projects", [
    F("name", required=True), F("owner_id", "Owner", type="fk", fk=User, fk_label=lambda x: x.name), F("due", type="date"),
    F("status", type="select", choices=["Active", "On Hold", "Complete"]), F("color", list=False), F("description", type="text", list=False),
], singular="Project", order_by=Project.due, nav="tasks.projects", row_link=lambda p: u("board", project=p.id)).register(bp)

Resource("tasks", "recurring", RecurringTask, "Recurring", [
    F("title", required=True), F("frequency", type="select", choices=["Daily", "Weekly", "Monthly", "Quarterly", "Annual"]), F("next_due", type="date"),
    F("assignee_id", "Assignee", type="fk", fk=User, fk_label=lambda x: x.name), F("project_id", "Project", type="fk", fk=Project),
    F("priority", type="select", choices=PRIORITIES), F("active", type="bool", default=True),
], singular="Recurring task", order_by=RecurringTask.next_due, nav="tasks.recurring").register(bp)

Resource("tasks", "meetings", Meeting, "Meetings", [
    F("title", required=True), F("day", "When", type="datetime"), F("attendees"), F("agenda", type="text", list=False), F("notes", type="text", list=False),
], singular="Meeting", order_by=Meeting.day.desc(), nav="tasks.meetings", row_link=lambda m: u("meeting", mid=m.id),
    after_save=lambda m: u("meeting", mid=m.id)).register(bp)


def filtered():
    q = live()
    a = request.args
    if a.get("who", "all") == "mine":
        q = q.filter(Task.assignee_id == current_user.id)
    elif a.get("who", "").isdigit():
        q = q.filter(Task.assignee_id == int(a["who"]))
    if a.get("project"):
        q = q.filter(Task.project_id == int(a["project"]))
    if a.get("priority"):
        q = q.filter(Task.priority == a["priority"])
    if a.get("app"):
        q = q.filter(Task.app == a["app"])
    if a.get("q"):
        q = q.filter(Task.title.ilike(f"%{a['q']}%"))
    return q.order_by(Task.due).all()


def filter_bar(view):
    a = request.args
    def sel(name, opts, label):
        o = "".join(f'<option value="{escape(v)}" {"selected" if a.get(name, "") == str(v) else ""}>{escape(l)}</option>' for v, l in [("", label)] + opts)
        return f'<select class="inp" name="{name}" onchange="this.form.submit()" style="width:auto">{o}</select>'
    who = a.get("who", "all")
    base = {k: v for k, v in a.items() if k != "who"}
    toggle = (f'<a class="chip {"on" if who == "mine" else ""}" href="{u(view, who="mine", **base)}">Mine</a>'
              f'<a class="chip {"on" if who == "all" else ""}" href="{u(view, who="all", **base)}">All</a>')
    views = (f'<a class="chip {"on" if view == "board" else ""}" href="{u("board", **a)}">Pipeline</a>'
             f'<a class="chip {"on" if view == "table_view" else ""}" href="{u("table_view", **a)}">Table</a>')
    return Markup(f'<form method="get" class="chips" style="gap:8px">{toggle}<span style="width:12px"></span>{views}<span style="flex:1"></span>'
                  f'<input type="hidden" name="who" value="{escape(who)}">'
                  f'<input class="inp" name="q" value="{escape(a.get("q", ""))}" placeholder="Search tasks…" style="width:200px">'
                  + sel("project", [(p.id, p.name) for p in Project.query.order_by(Project.name)], "All projects")
                  + sel("priority", [(p, p) for p in PRIORITIES], "Any priority") + sel("app", [(x, x) for x in APP_CHOICES], "Any app") + "</form>")


def tcard(t):
    due = f'<span class="small {"neg" if t.overdue else "muted"}">{t.due:%b %d}</span>' if t.due else ""
    proj = f'<span class="small" style="color:{escape(t.project.color)}">● {escape(t.project.name)}</span>' if t.project else ""
    return (f'<div class="kcard" draggable="true" data-id="{t.id}"><a href="{u("task", tid=t.id)}" style="font-weight:600;color:var(--ink)">{escape(t.title)}</a>'
            f'<div style="display:flex;gap:6px;align-items:center;margin-top:6px;flex-wrap:wrap">{pill(t.priority, PRI_TONE.get(t.priority, "gray"))}{proj}</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">'
            f'<span class="av" title="{escape(t.assignee.name if t.assignee else "")}" style="background:{t.assignee.color if t.assignee else "#94a3b8"}">'
            f'{escape(t.assignee.initials if t.assignee else "?")}</span>{due}</div></div>')


BOARD_JS = """<style>.kb{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.kcol{background:#f1f5f9;border-radius:12px;padding:10px;min-height:300px}
.kcol h4{margin:2px 4px 10px;font-size:12px;display:flex;justify-content:space-between}.kcard{display:block!important;background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:8px;cursor:grab}.kcard>a{display:block}.kcard>div{display:flex!important}
.kcol.over{outline:2px dashed var(--accent)}.av{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;color:#fff;font-size:10px;font-weight:700}</style>
<script>document.addEventListener('DOMContentLoaded',function(){var tok=JSON.parse(document.body.getAttribute('hx-headers'))['X-CSRFToken'];
document.querySelectorAll('.kcard').forEach(function(c){c.addEventListener('dragstart',function(e){e.dataTransfer.setData('text',c.dataset.id)})});
document.querySelectorAll('.kcol').forEach(function(col){col.addEventListener('dragover',function(e){e.preventDefault();col.classList.add('over')});
col.addEventListener('dragleave',function(){col.classList.remove('over')});
col.addEventListener('drop',function(e){e.preventDefault();var id=e.dataTransfer.getData('text');var fd=new FormData();fd.append('status',col.dataset.status);fd.append('csrf_token',tok);
fetch('TASKS_BASE'+id+'/status',{method:'POST',body:fd,headers:{'X-Requested-With':'fetch'}}).then(function(){location.reload()})})})});</script>"""


@bp.route("/")
def dashboard():
    return board()


@bp.route("/board/")
def board():
    ts = filtered()
    cols = defaultdict(list)
    for t in ts:
        cols[t.status].append(t)
    h = '<div class="kb">' + "".join(
        f'<div class="kcol" data-status="{s}"><h4><span>{s}</span><span class="muted">{len(cols[s])}</span></h4>' + "".join(tcard(t) for t in cols[s]) + "</div>" for s in BOARD) + "</div>"
    other = [t for t in ts if t.status not in BOARD]
    mine_open = live().filter(Task.assignee_id == current_user.id, Task.status.notin_(["Done", "Canceled"])).count()
    over = len([t for t in ts if t.overdue])
    return render("Tasks", [
        kpis([("Open", len([t for t in ts if t.status not in ("Done", "Canceled")]), "in this view", "", "#2563eb"), ("Mine", mine_open, "assigned to me", "", "#7c3aed"),
              ("Overdue", over, "", "neg" if over else "", "#ef4444"), ("Waiting sign-off", len(cols["Done – Waiting Sign Off"]), "", "warn", "#f59e0b")]),
        html(str(filter_bar("board"))), html(h + BOARD_JS.replace("TASKS_BASE", url_for("tasks.task", tid=0).rsplit("0/", 1)[0])),
        card(f"On hold, done and canceled · {len(other)}", table(["Task", "Status", "Assignee", "Due"], [[link(t.title, u("task", tid=t.id)), status(t.status),
                                                                                                         t.assignee.name if t.assignee else "—", D(t.due)] for t in other], max_height=300)),
    ], active="tasks.board", actions=[("+ New task", u("tasks_new"), "primary")])


@bp.route("/table/")
def table_view():
    ts = filtered()
    rows = [[link(t.title, u("task", tid=t.id)), status(t.status), pill(t.priority, PRI_TONE.get(t.priority, "gray")), t.assignee.name if t.assignee else "—",
             t.project.name if t.project else "—", t.app or "—", Markup(f'<span class="{"neg" if t.overdue else ""}">{D(t.due)}</span>')] for t in ts]
    return render("Tasks", [html(str(filter_bar("table_view"))), card(None, table(["Task", "Status", "Priority", "Assignee", "Project", "App", "Due"], rows))],
                  active="tasks.board", actions=[("Export CSV", u("tasks_export")), ("+ New task", u("tasks_new"), "primary")])


def can_move(t, new):
    if not current_user.can_write:
        return False
    if t.status == "Done – Waiting Sign Off" and new == "Done" and st.get("tasks", "signoff_required", "yes") == "yes":
        return current_user.is_admin
    return True


@bp.route("/<int:tid>/status", methods=["POST"])
def set_status(tid):
    t = db.get_or_404(Task, tid)
    new = request.form.get("status")
    if new not in TASK_STATUSES:
        abort(400)
    if not can_move(t, new):
        if request.headers.get("X-Requested-With") == "fetch":
            flash("Only an admin can sign off a task.", "error")
            return ("forbidden", 403)
        abort(403)
    old, t.status = t.status, new
    t.completed_at = datetime.utcnow() if new == "Done" else None
    db.session.add(TaskComment(task_id=t.id, user_id=current_user.id, body=f"Moved from {old} to {new}."))
    audit("tasks", "status", "task", t.id, f"{t.title}: {old} → {new}")
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return ("ok", 200)
    return redirect(request.referrer or u("task", tid=t.id))


@bp.route("/<int:tid>/")
def task(tid):
    t = db.get_or_404(Task, tid)
    nxt = {"To Do": ["In Progress"], "In Progress": ["Done – Waiting Review", "On Hold"], "Done – Waiting Review": ["Done – Waiting Sign Off", "In Progress"],
           "Done – Waiting Sign Off": ["Done", "In Progress"], "On Hold": ["To Do", "In Progress"], "Done": ["In Progress"], "Canceled": ["To Do"]}.get(t.status, [])
    btns = " ".join(str(postbtn(u("set_status", tid=t.id), f"→ {s}", "btn sm primary" if i == 0 else "btn sm", f'<input type="hidden" name="status" value="{s}">'))
                    for i, s in enumerate(nxt))
    comments = lst([(c.body, f"{c.user.name if c.user else '—'} · {c.created_at:%b %d, %H:%M}") for c in t.comments], empty="No comments yet.")
    actions = [("Edit", u("tasks_edit", obj_id=t.id))]
    if t.deleted_at:
        actions.append(("post", "Restore", u("restore", tid=t.id), "primary", None))
    else:
        actions.append(("post", "Move to trash", u("tasks_delete", obj_id=t.id), "", "Move this task to the trash?"))
    return render(t.title, [
        row(card("Details", [table(["Field", "Value"], [["Status", status(t.status)], ["Priority", pill(t.priority, PRI_TONE.get(t.priority, "gray"))],
                                                        ["Assignee", t.assignee.name if t.assignee else "—"], ["Reviewer", t.reviewer.name if t.reviewer else "—"],
                                                        ["Project", t.project.name if t.project else "—"], ["Related app", t.app or "—"], ["Due", D(t.due)],
                                                        ["Meeting", link(t.meeting.title, u("meeting", mid=t.meeting_id)) if t.meeting else "—"],
                                                        ["Created by", t.created_by.name if t.created_by else "—"]], sortable=False),
                             html(f'<div style="padding:12px 16px" class="small">{escape(t.description or "")}</div>'),
                             html(f'<div style="padding:0 16px 14px;display:flex;gap:6px;flex-wrap:wrap">{btns}</div>')]),
            card("Activity", [comments, form(u("comment", tid=t.id), [("body", "Add a comment", "textarea", "")], submit="Comment")], flush=False)),
    ], back=("Board", u("board")), active="tasks.board", actions=actions, sub=f"Task #{t.id}")


@bp.route("/<int:tid>/comment", methods=["POST"])
@write_required
def comment(tid):
    t = db.get_or_404(Task, tid)
    body = (request.form.get("body") or "").strip()
    if body:
        db.session.add(TaskComment(task_id=t.id, user_id=current_user.id, body=body))
        db.session.commit()
    return redirect(u("task", tid=t.id))


@bp.route("/<int:tid>/restore", methods=["POST"])
@write_required
def restore(tid):
    t = db.get_or_404(Task, tid)
    t.deleted_at = None
    audit("tasks", "restore", "task", t.id, t.title)
    db.session.commit()
    flash("Task restored.", "success")
    return redirect(u("task", tid=t.id))


@bp.route("/<int:tid>/purge", methods=["POST"])
@write_required
def purge(tid):
    if not current_user.is_admin:
        abort(403)
    t = db.get_or_404(Task, tid)
    audit("tasks", "purge", "task", t.id, t.title)
    db.session.delete(t)
    db.session.commit()
    flash("Task permanently deleted.", "success")
    return redirect(u("deleted"))


@bp.route("/projects/")
def projects():
    ps = Project.query.order_by(Project.due).all()
    rows = []
    for p in ps:
        ts = [t for t in p.tasks if not t.deleted_at]
        done = len([t for t in ts if t.status == "Done"])
        pct = done / (len(ts) or 1) * 100
        bar = Markup(f'<div style="background:#e2e8f0;border-radius:6px;height:8px;width:140px"><div style="width:{pct:.0f}%;background:{escape(p.color)};height:8px;border-radius:6px"></div></div>')
        rows.append([link(p.name, u("board", project=p.id)), p.owner.name if p.owner else "—", D(p.due), len(ts), done, bar, status(p.status),
                     link("Edit", u("projects_edit", obj_id=p.id))])
    return render("Projects", [card(None, table(["Project", "Owner", "Due", ">Tasks", ">Done", "Progress", "Status", ""], rows))],
                  actions=[("+ New project", u("projects_new"), "primary")])


FREQ = {"Daily": 1, "Weekly": 7, "Monthly": 30, "Quarterly": 91, "Annual": 365}


def spawn(r):
    t = Task(title=f"{r.title} — {r.next_due:%b %d}", status="To Do", priority=r.priority, assignee_id=r.assignee_id, project_id=r.project_id, due=r.next_due,
             recurring_id=r.id, created_by_id=current_user.id if current_user.is_authenticated else None)
    db.session.add(t)
    nd = r.next_due
    if r.frequency == "Monthly":
        nd = (nd.replace(day=1) + timedelta(days=32)).replace(day=min(nd.day, 28))
    else:
        nd = nd + timedelta(days=FREQ.get(r.frequency, 30))
    r.next_due = nd
    return t


@bp.route("/recurring/")
def recurring():
    rs = RecurringTask.query.order_by(RecurringTask.next_due).all()
    rows = [[link(r.title, u("recurring_edit", obj_id=r.id)), r.frequency, D(r.next_due), r.assignee.name if r.assignee else "—", r.project.name if r.project else "—",
             status("Active") if r.active else status("Closed"), postbtn(u("spawn_now", rid=r.id), "Create next task") if r.active else ""] for r in rs]
    return render("Recurring", [note("Each recurring item creates its next task on the due date (or now, with the button) and rolls its date forward."),
                                card(None, table(["Checklist", "Frequency", "Next due", "Assignee", "Project", "Status", ""], rows))],
                  actions=[("post", "Create all due today", u("spawn_due"), "", None), ("+ New recurring", u("recurring_new"), "primary")])


@bp.route("/recurring/<int:rid>/spawn", methods=["POST"])
@write_required
def spawn_now(rid):
    r = db.get_or_404(RecurringTask, rid)
    t = spawn(r)
    db.session.flush()
    audit("tasks", "spawn", "recurring", r.id, t.title)
    db.session.commit()
    flash(f"Created “{t.title}”. Next due {r.next_due:%b %d}.", "success")
    return redirect(u("recurring"))


@bp.route("/recurring/spawn-due", methods=["POST"])
@write_required
def spawn_due():
    n = 0
    for r in RecurringTask.query.filter(RecurringTask.active.is_(True), RecurringTask.next_due <= date.today()).all():
        spawn(r)
        n += 1
    db.session.commit()
    flash(f"Created {n} task(s).", "success")
    return redirect(u("recurring"))


@bp.route("/meetings/")
def meetings():
    ms = Meeting.query.order_by(Meeting.day.desc()).all()
    rows = [[link(m.title, u("meeting", mid=m.id)), D(m.day), m.attendees, len([t for t in m.tasks if not t.deleted_at]),
             len([t for t in m.tasks if not t.deleted_at and t.status not in ("Done", "Canceled")])] for m in ms]
    return render("Meetings", [card(None, table(["Meeting", "Date", "Attendees", ">Action items", ">Open"], rows))], actions=[("+ New meeting", u("meetings_new"), "primary")])


@bp.route("/meetings/<int:mid>/", methods=["GET", "POST"])
def meeting(mid):
    m = db.get_or_404(Meeting, mid)
    if request.method == "POST":
        if not current_user.can_write:
            abort(403)
        title = (request.form.get("title") or "").strip()
        if title:
            aid = request.form.get("assignee_id")
            d = request.form.get("due")
            t = Task(title=title, meeting_id=m.id, assignee_id=int(aid) if aid else None, due=date.fromisoformat(d) if d else None, created_by_id=current_user.id)
            db.session.add(t)
            db.session.flush()
            audit("tasks", "create", "task", t.id, f"from meeting {m.title}")
            db.session.commit()
            flash("Action item added.", "success")
        return redirect(u("meeting", mid=m.id))
    items = [t for t in m.tasks if not t.deleted_at]
    return render(m.title, [
        row(card("Notes", html(f'<div style="padding:14px 16px;white-space:pre-wrap" class="small"><b>Attendees:</b> {escape(m.attendees or "")}\n\n<b>Agenda</b>\n'
                               f'{escape(m.agenda or "")}\n\n<b>Notes</b>\n{escape(m.notes or "")}</div>')),
            card("Action items", [table(["Task", "Owner", "Due", "Status"], [[link(t.title, u("task", tid=t.id)), t.assignee.name if t.assignee else "—", D(t.due), status(t.status)]
                                                                           for t in items], empty="No action items."),
                                  form(u("meeting", mid=m.id), [("title", "New action item", "text", ""), ("assignee_id", "Owner", "select", [(x.id, x.name) for x in staff()]),
                                                                ("due", "Due", "date", "")], submit="Add action item")], flush=False)),
    ], back=("Meetings", u("meetings")), active="tasks.meetings", sub=f"{m.day:%A, %B %d, %Y}", actions=[("Edit", u("meetings_edit", obj_id=m.id))])


@bp.route("/outstanding/")
def outstanding():
    ts = live().filter(Task.status.notin_(["Done", "Canceled"])).order_by(Task.due).all()
    by = defaultdict(list)
    for t in ts:
        by[t.assignee.name if t.assignee else "Unassigned"].append(t)
    names = sorted(by, key=lambda n: -len(by[n]))
    blocks = [row(card("Open by person", chart(bar_chart(names, [len(by[n]) for n in names], "Open tasks", money=False, color="#2563eb"), 220)),
                  card("By status", chart(donut(BOARD + ["On Hold"], [len([t for t in ts if t.status == s]) for s in BOARD + ["On Hold"]], money=False), 220)))]
    for n in names:
        blocks.append(card(f"{n} · {len(by[n])} open · {len([t for t in by[n] if t.overdue])} overdue",
                           table(["Task", "Status", "Priority", "Due"], [[link(t.title, u("task", tid=t.id)), status(t.status), pill(t.priority, PRI_TONE.get(t.priority, "gray")),
                                                                       Markup(f'<span class="{"neg" if t.overdue else ""}">{D(t.due)}</span>')] for t in by[n]], sortable=False)))
    return render("All Outstanding", blocks, sub=f"{len(ts)} open tasks")


@bp.route("/deleted/")
def deleted():
    ts = Task.query.filter(Task.deleted_at.isnot(None)).order_by(Task.deleted_at.desc()).all()
    return render("Deleted", [card(None, table(["Task", "Deleted", "Assignee", ""], [[link(t.title, u("task", tid=t.id)), D(t.deleted_at), t.assignee.name if t.assignee else "—",
                                                                                  postbtn(u("restore", tid=t.id), "Restore") + Markup(" ") + postbtn(u("purge", tid=t.id), "Delete forever", "btn sm red")]
                                                                                 for t in ts], empty="Trash is empty."))])


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    r = st.handle("tasks", SETTINGS)
    if r:
        return r
    return render("Settings", [card("Workflow", form(u("settings"), st.form_fields("tasks", SETTINGS)), flush=False)])

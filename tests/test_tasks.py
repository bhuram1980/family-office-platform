from app.extensions import db
from app.models import Meeting, RecurringTask, Task, User


def test_board_and_pages(admin):
    for url in ["/tasks/", "/tasks/board/?who=mine", "/tasks/table/?priority=High", "/tasks/projects/", "/tasks/recurring/", "/tasks/meetings/",
                "/tasks/outstanding/", "/tasks/deleted/", "/tasks/settings/", "/tasks/tasks/new"]:
        assert admin.get(url).status_code == 200, url


def test_create_move_and_soft_delete(admin):
    r = admin.post("/tasks/tasks/new", {"title": "Write test memo", "status": "To Do", "priority": "High"})
    t = Task.query.filter_by(title="Write test memo").one()
    assert r.headers["Location"].endswith(f"/tasks/{t.id}/")
    assert t.reviewer is not None and t.created_by.username == "tirumala"
    admin.post(f"/tasks/{t.id}/status", {"status": "In Progress"})
    db.session.refresh(t)
    assert t.status == "In Progress" and t.comments
    admin.post(f"/tasks/tasks/{t.id}/delete")
    db.session.refresh(t)
    assert t.deleted_at is not None
    assert b"Write test memo" in admin.get("/tasks/deleted/").data
    admin.post(f"/tasks/{t.id}/restore")
    db.session.refresh(t)
    assert t.deleted_at is None


def test_signoff_needs_admin(login_as):
    t = Task.query.filter_by(status="Done – Waiting Sign Off").first() or Task.query.first()
    t.status = "Done – Waiting Sign Off"
    db.session.commit()
    analyst = login_as("elena")
    assert analyst.post(f"/tasks/{t.id}/status", {"status": "Done"}).status_code == 403
    boss = login_as("tirumala")
    boss.post(f"/tasks/{t.id}/status", {"status": "Done"})
    db.session.refresh(t)
    assert t.status == "Done" and t.completed_at


def test_recurring_spawn_rolls_date(admin):
    r = RecurringTask.query.filter_by(frequency="Weekly").first()
    d0 = r.next_due
    admin.post(f"/tasks/recurring/{r.id}/spawn")
    db.session.refresh(r)
    assert (r.next_due - d0).days == 7
    assert Task.query.filter_by(recurring_id=r.id).count() == 1


def test_meeting_action_item(admin):
    m = Meeting.query.first()
    u = User.query.filter_by(username="noah").one()
    admin.post(f"/tasks/meetings/{m.id}/", {"title": "Follow up with lender", "assignee_id": u.id, "due": "2030-01-05"})
    t = Task.query.filter_by(title="Follow up with lender").one()
    assert t.meeting_id == m.id and t.assignee_id == u.id

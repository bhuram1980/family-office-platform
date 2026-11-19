"""Tasks: the office work queue."""
from datetime import date, datetime

from ..extensions import db
from .core import TimestampMixin

TASK_STATUSES = ["To Do", "In Progress", "Done – Waiting Review", "Done – Waiting Sign Off", "On Hold", "Done", "Canceled"]
BOARD = TASK_STATUSES[:4]
PRIORITIES = ["Urgent", "High", "Normal", "Low"]


class Project(TimestampMixin, db.Model):
    __tablename__ = "tk_projects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    color = db.Column(db.String(9), default="#2563eb")
    due = db.Column(db.Date)
    status = db.Column(db.String(20), default="Active")
    description = db.Column(db.Text)
    owner = db.relationship("User")

    def __str__(self):
        return self.name


class RecurringTask(TimestampMixin, db.Model):
    __tablename__ = "tk_recurring"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    frequency = db.Column(db.String(20), default="Monthly")
    next_due = db.Column(db.Date)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    project_id = db.Column(db.Integer, db.ForeignKey("tk_projects.id"))
    priority = db.Column(db.String(10), default="Normal")
    active = db.Column(db.Boolean, default=True)
    assignee = db.relationship("User")
    project = db.relationship("Project")

    def __str__(self):
        return self.title


class Meeting(TimestampMixin, db.Model):
    __tablename__ = "tk_meetings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    day = db.Column(db.DateTime, default=datetime.utcnow)
    attendees = db.Column(db.String(300))
    agenda = db.Column(db.Text)
    notes = db.Column(db.Text)

    def __str__(self):
        return f"{self.title} ({self.day:%b %d})"


class Task(TimestampMixin, db.Model):
    __tablename__ = "tk_tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default="To Do", index=True)
    priority = db.Column(db.String(10), default="Normal")
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    project_id = db.Column(db.Integer, db.ForeignKey("tk_projects.id"))
    meeting_id = db.Column(db.Integer, db.ForeignKey("tk_meetings.id"))
    recurring_id = db.Column(db.Integer, db.ForeignKey("tk_recurring.id"))
    app = db.Column(db.String(30))  # which app it relates to
    due = db.Column(db.Date)
    completed_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    assignee = db.relationship("User", foreign_keys=[assignee_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    project = db.relationship("Project", backref="tasks")
    meeting = db.relationship("Meeting", backref="tasks")
    recurring = db.relationship("RecurringTask")

    @property
    def overdue(self):
        return self.due and self.due < date.today() and self.status not in ("Done", "Canceled")

    def __str__(self):
        return self.title


class TaskComment(db.Model):
    __tablename__ = "tk_comments"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tk_tasks.id", ondelete="CASCADE"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    task = db.relationship("Task", backref=db.backref("comments", cascade="all, delete-orphan", order_by="TaskComment.created_at"))
    user = db.relationship("User")

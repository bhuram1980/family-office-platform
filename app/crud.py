"""Tiny declarative CRUD framework shared by every app.

A Resource describes a model, its form fields and list columns. ``register``
adds list / new / edit / delete / CSV-export routes to an app blueprint, all
rendered inside the shared shell, audited, and permission-checked.
"""
import csv
import io
from datetime import date, datetime

from flask import (abort, flash, redirect, render_template, request,
                   Response, url_for)
from flask_login import current_user
from sqlalchemy import or_, String, Text, cast

from .extensions import db
from .services.audit import audit


class Field:
    def __init__(self, name, label=None, type="str", choices=None, required=False,
                 fk=None, fk_label=None, help=None, default=None, list=True,
                 fmt=None, form=True, align=None):
        self.name = name
        self.label = label or name.replace("_", " ").title()
        self.type = type  # str text int float money date bool select fk email
        self.choices = choices
        self.required = required
        self.fk = fk  # model class for foreign key
        self.fk_label = fk_label or (lambda o: str(o))
        self.help = help
        self.default = default
        self.list = list
        self.fmt = fmt
        self.form = form
        self.align = align or ("r" if type in ("int", "float", "money") else None)

    def options(self):
        if self.type == "select":
            ch = self.choices() if callable(self.choices) else self.choices
            return [(c, c) if not isinstance(c, tuple) else c for c in ch]
        if self.type == "fk":
            return [(o.id, self.fk_label(o)) for o in self.fk.query.all()]
        return []

    def parse(self, raw):
        if self.type == "bool":
            return raw in ("on", "true", "1", "yes")
        if raw is None or str(raw).strip() == "":
            return None
        raw = str(raw).strip()
        if self.type == "int" or self.type == "fk":
            return int(float(raw.replace(",", "")))
        if self.type in ("float", "money"):
            return float(raw.replace(",", "").replace("$", ""))
        if self.type == "date":
            return date.fromisoformat(raw)
        if self.type == "datetime":
            return datetime.fromisoformat(raw)
        return raw

    def display(self, obj):
        v = getattr(obj, self.name, None)
        if self.fmt:
            return self.fmt(obj)
        if self.type == "fk":
            rel = getattr(obj, self.name.removesuffix("_id"), None)
            return self.fk_label(rel) if rel else "—"
        if v is None:
            return "—"
        if self.type == "money":
            return f"${v:,.0f}"
        if self.type == "float":
            return f"{v:,.2f}"
        if self.type == "bool":
            return "Yes" if v else "No"
        if self.type == "date":
            return v.strftime("%b %d, %Y")
        return v


class Resource:
    registry = {}

    def __init__(self, app_id, slug, model, title, fields, singular=None,
                 order_by=None, search=None, filters=None, per_page=50,
                 subtitle=None, nav=None, row_link=None, readonly=False,
                 query=None, extra_actions=None):
        self.app_id = app_id
        self.slug = slug
        self.model = model
        self.title = title
        self.singular = singular or title.rstrip("s")
        self.fields = fields
        self.order_by = order_by
        self.search = search or [f.name for f in fields if f.type in ("str", "text", "email")][:3]
        self.filters = filters or []  # field names rendered as chips
        self.per_page = per_page
        self.subtitle = subtitle
        self.nav = nav  # endpoint used to highlight sidebar
        self.row_link = row_link
        self.readonly = readonly
        self.query = query
        self.extra_actions = extra_actions or []
        Resource.registry[(app_id, slug)] = self

    @property
    def list_fields(self):
        return [f for f in self.fields if f.list]

    @property
    def form_fields(self):
        return [f for f in self.fields if f.form]

    def endpoint(self, action):
        return f"{self.bp_name}.{self.slug.replace('-', '_')}_{action}"

    def base_query(self):
        q = self.query() if self.query else self.model.query
        return q

    # ------------------------------------------------------------------
    def register(self, bp):
        self.bp_name = bp.name
        ep = self.slug.replace("-", "_")
        bp.add_url_rule(f"/{self.slug}/", f"{ep}_list", self.view_list)
        bp.add_url_rule(f"/{self.slug}/export.csv", f"{ep}_export", self.view_export)
        bp.add_url_rule(f"/{self.slug}/new", f"{ep}_new", self.view_form, methods=["GET", "POST"])
        bp.add_url_rule(f"/{self.slug}/<int:obj_id>/edit", f"{ep}_edit", self.view_form, methods=["GET", "POST"])
        bp.add_url_rule(f"/{self.slug}/<int:obj_id>/delete", f"{ep}_delete", self.view_delete, methods=["POST"])
        return self

    def filtered(self):
        q = self.base_query()
        term = request.args.get("q", "").strip()
        if term and self.search:
            q = q.filter(or_(*[cast(getattr(self.model, s), String).ilike(f"%{term}%") for s in self.search]))
        for fname in self.filters:
            val = request.args.get(fname)
            if val:
                q = q.filter(getattr(self.model, fname) == val)
        sort = request.args.get("sort")
        if sort and hasattr(self.model, sort.lstrip("-")):
            col = getattr(self.model, sort.lstrip("-"))
            q = q.order_by(col.desc() if sort.startswith("-") else col.asc())
        elif self.order_by is not None:
            q = q.order_by(*(self.order_by if isinstance(self.order_by, (list, tuple)) else [self.order_by]))
        return q

    def filter_values(self, fname):
        f = next(x for x in self.fields if x.name == fname)
        if f.choices:
            return [o[0] for o in f.options()]
        col = getattr(self.model, fname)
        return [r[0] for r in db.session.query(col).distinct().order_by(col) if r[0]]

    def view_list(self):
        page = max(int(request.args.get("page", 1) or 1), 1)
        pag = self.filtered().paginate(page=page, per_page=self.per_page, error_out=False)
        return render_template("crud/list.html", r=self, pag=pag, items=pag.items)

    def view_export(self):
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow([f.label for f in self.fields])
        for o in self.filtered().all():
            w.writerow([getattr(o, f.name) for f in self.fields])
        audit(self.app_id, "export", self.slug, None, f"CSV export of {self.title}")
        db.session.commit()
        return Response(out.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={self.slug}.csv"})

    def view_form(self, obj_id=None):
        obj = db.session.get(self.model, obj_id) if obj_id else None
        if obj_id and not obj:
            abort(404)
        if request.method == "POST":
            if not current_user.can_write or self.readonly:
                abort(403)
            is_new = obj is None
            obj = obj or self.model()
            errors = []
            for f in self.form_fields:
                raw = request.form.get(f.name)
                try:
                    val = f.parse(raw)
                except (ValueError, TypeError):
                    errors.append(f"{f.label}: invalid value")
                    continue
                if f.required and val in (None, ""):
                    errors.append(f"{f.label} is required")
                    continue
                setattr(obj, f.name, val)
            if errors:
                db.session.rollback()
                for e in errors:
                    flash(e, "error")
                return render_template("crud/form.html", r=self, obj=obj, values=request.form), 400
            if is_new:
                db.session.add(obj)
            db.session.flush()
            audit(self.app_id, "create" if is_new else "update", self.slug, obj.id, str(obj))
            db.session.commit()
            flash(f"{self.singular} {'created' if is_new else 'saved'}.", "success")
            nxt = request.form.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else url_for(self.endpoint("list")))
        return render_template("crud/form.html", r=self, obj=obj, values=None)

    def view_delete(self, obj_id):
        if not current_user.can_write or self.readonly:
            abort(403)
        obj = db.session.get(self.model, obj_id) or abort(404)
        label = str(obj)
        try:
            db.session.delete(obj)
            audit(self.app_id, "delete", self.slug, obj_id, label)
            db.session.commit()
            flash(f"{self.singular} deleted.", "success")
        except Exception:
            db.session.rollback()
            flash(f"Can't delete {label}: other records depend on it.", "error")
        nxt = request.form.get("next")
        return redirect(nxt if nxt and nxt.startswith("/") else url_for(self.endpoint("list")))

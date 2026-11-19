"""Deal Evaluator: inbox to IC, weighted scoring, side-by-side comparison, follow-ups, and conversion into a ledger investment."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import Deal, DealActivity, DealScore, Entity, FollowUp, Investment, User
from ..models.deals import CRITERIA, DEAL_STAGES
from ..pages import D, M, MS, b, bar_chart, card, chart, donut, form, html, kpis, link, lst, note, pill, render, row, status, table, tabs
from ..services import settings as st
from ..services.audit import audit
from .common import make_bp, write_required

bp = make_bp("deals", "deals")
OPEN = ["Inbox", "Screening", "Diligence", "IC Review"]
STAGE_TONE = {"Inbox": "gray", "Screening": "blue", "Diligence": "blue", "IC Review": "amber", "Approved": "green", "Closed": "green", "Passed": "red"}
SETTINGS = [(f"w_{c.lower().replace(' ', '_')}", f"Weight · {c}", "1", "number") for c in CRITERIA] + [
    ("min_score_ic", "Minimum score to send to IC", "3.2", "number"), ("stale_days", "Flag deals untouched for (days)", "21", "number")]


def u(ep, **kw):
    return url_for(f"deals.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return Markup(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                  f'<button class="{cls}">{escape(label)}</button></form>')


def weights():
    return {c: st.get("deals", f"w_{c.lower().replace(' ', '_')}", 1.0, float) for c in CRITERIA}


def score(d, w=None):
    w = w or weights()
    s = [(x.score, w.get(x.criterion, 1)) for x in d.scores if x.score]
    tw = sum(v for _, v in s)
    return round(sum(a * v for a, v in s) / tw, 2) if tw else None


def sbadge(v):
    if v is None:
        return pill("unscored", "gray")
    return pill(f"{v:.1f}", "green" if v >= 3.8 else "amber" if v >= 3 else "red")


def dlink(d):
    return link(d.name, u("deal", did=d.id), "tk")


def log(d, text):
    db.session.add(DealActivity(deal_id=d.id, user_id=current_user.id, text=text))


Resource("deals", "deals", Deal, "Deals", [
    F("name", required=True), F("sponsor"), F("asset_class", "Asset class", type="select",
                                              choices=["Private Equity", "Venture Capital", "Real Estate", "Private Credit", "Alternative Investments"]),
    F("sector"), F("location"), F("stage", type="select", choices=DEAL_STAGES, default="Inbox"), F("size", "Deal size", type="money"),
    F("check_size", "Our check", type="money"), F("target_irr", "Target IRR %", type="float"), F("target_moic", "Target MOIC", type="float"),
    F("hold_years", "Hold (years)", type="float", list=False), F("source", type="select", choices=["GP relationship", "Banker", "Co-investor referral", "Inbound", "Family network", "Conference"]),
    F("owner_id", "Owner", type="fk", fk=User, fk_label=lambda x: x.name), F("received", type="date", list=False), F("next_step", list=False),
    F("thesis", type="text", list=False), F("risks", type="text", list=False), F("pass_reason", list=False),
], singular="Deal", order_by=Deal.received.desc(), filters=["stage", "asset_class"], nav="deals.pipeline",
    on_save=lambda d, new: d.owner_id or setattr(d, "owner_id", current_user.id), after_save=lambda d: u("deal", did=d.id), row_link=lambda d: u("deal", did=d.id)).register(bp)

Resource("deals", "followup-records", FollowUp, "Follow-ups", [
    F("deal_id", "Deal", type="fk", fk=Deal, required=True), F("note", required=True), F("owner_id", "Owner", type="fk", fk=User, fk_label=lambda x: x.name),
    F("due", type="date"), F("done", type="bool"),
], singular="Follow-up", order_by=FollowUp.due, nav="deals.followups").register(bp)


@bp.route("/")
def dashboard():
    deals = Deal.query.all()
    w = weights()
    by = defaultdict(list)
    for d in deals:
        by[d.stage].append(d)
    openl = [d for d in deals if d.stage in OPEN]
    fus = FollowUp.query.filter_by(done=False).order_by(FollowUp.due).all()
    overdue = [f for f in fus if f.due and f.due < date.today()]
    stale_days = st.get("deals", "stale_days", 21, float)
    stale = []
    for d in openl:
        last = max((a.at for a in d.activity), default=datetime.combine(d.received, datetime.min.time()))
        if (datetime.utcnow() - last).days > stale_days:
            stale.append((d, (datetime.utcnow() - last).days))
    top = sorted([d for d in openl if score(d, w)], key=lambda d: -score(d, w))[:6]
    closed = [d for d in deals if d.stage in ("Approved", "Closed")]
    decided = closed + by["Passed"]
    return render("Deal Evaluator", [
        kpis([("Open pipeline", len(openl), MS(sum(d.check_size or 0 for d in openl)) + " of checks", "", "#4f46e5"), ("In diligence", len(by["Diligence"]), "", "", "#0ea5e9"),
              ("At IC", len(by["IC Review"]), "", "warn" if by["IC Review"] else "", "#f59e0b"), ("Approved / closed", len(closed), "", "pos", "#10b981"),
              ("Hit rate", f"{len(closed) / (len(decided) or 1) * 100:.0f}%", f"{len(decided)} decided", "", "#8b5cf6"),
              ("Follow-ups overdue", len(overdue), f"{len(fus)} open", "neg" if overdue else "", "#ef4444")]),
        row(card("Pipeline by stage", chart(bar_chart(DEAL_STAGES, [len(by[s]) for s in DEAL_STAGES], "Deals", money=False, color="#4f46e5"), 230)),
            card("Open pipeline by asset class", chart(donut(sorted({d.asset_class for d in openl}), [sum(d.check_size or 0 for d in openl if d.asset_class == c)
                                                                                                    for c in sorted({d.asset_class for d in openl})]), 230))),
        row(card("Highest-scoring open deals", table(["Deal", "Stage", ">Score", ">Check"], [[dlink(d), pill(d.stage, STAGE_TONE[d.stage]), sbadge(score(d, w)), M(d.check_size)]
                                                                                           for d in top], sortable=False), right=("Compare →", u("compare", ids=",".join(str(d.id) for d in top[:3])))),
            card("Follow-ups due", lst([(f.note, f"{f.deal.name} · {f.owner.name if f.owner else '—'}", D(f.due), "red" if f in overdue else "") for f in fus[:8]], empty="Nothing due."),
                 right=("All →", u("followups")))),
        card(f"Going stale (no activity in {stale_days:.0f}+ days)", table(["Deal", "Stage", "Owner", ">Days idle", "Next step"],
                                                                          [[dlink(d), pill(d.stage, STAGE_TONE[d.stage]), d.owner.name if d.owner else "—", n, d.next_step]
                                                                           for d, n in sorted(stale, key=lambda x: -x[1])], empty="Every open deal has recent activity.")),
    ], actions=[("Pipeline", u("pipeline")), ("+ New deal", u("deals_new"), "primary")])


@bp.route("/pipeline/")
def pipeline():
    view = request.args.get("view", "board")
    q = request.args.get("q", "")
    cls = request.args.get("cls", "")
    deals = Deal.query.order_by(Deal.received.desc()).all()
    if q:
        deals = [d for d in deals if q.lower() in (d.name + " " + (d.sponsor or "") + " " + (d.sector or "")).lower()]
    if cls:
        deals = [d for d in deals if d.asset_class == cls]
    w = weights()
    classes = sorted({d.asset_class for d in Deal.query.all() if d.asset_class})
    bar = (f'<form method="get" class="chips" style="gap:8px"><a class="chip {"on" if view == "board" else ""}" href="{u("pipeline", view="board", q=q, cls=cls)}">Board</a>'
           f'<a class="chip {"on" if view == "table" else ""}" href="{u("pipeline", view="table", q=q, cls=cls)}">Table</a><span style="flex:1"></span>'
           f'<input type="hidden" name="view" value="{escape(view)}"><input class="inp" name="q" value="{escape(q)}" placeholder="Search deals…" style="width:220px">'
           f'<select class="inp" name="cls" onchange="this.form.submit()" style="width:auto"><option value="">All asset classes</option>'
           + "".join(f'<option {"selected" if c == cls else ""}>{escape(c)}</option>' for c in classes) + "</select></form>")
    if view == "table":
        body = card(None, table(["Deal", "Sponsor", "Class", "Stage", ">Score", ">Size", ">Our check", ">Target IRR", "Owner", "Received"],
                                [[dlink(d), d.sponsor, d.asset_class, pill(d.stage, STAGE_TONE[d.stage]), sbadge(score(d, w)), M(d.size), M(d.check_size),
                                  f"{d.target_irr or 0:.1f}%", d.owner.name if d.owner else "—", D(d.received)] for d in deals]))
    else:
        cols = defaultdict(list)
        for d in deals:
            cols[d.stage].append(d)
        h = '<div class="kb" style="grid-template-columns:repeat(7,minmax(0,1fr))">' + "".join(
            f'<div class="kcol" data-status="{s}"><h4><span>{s}</span><span class="muted">{len(cols[s])}</span></h4>' + "".join(
                f'<div class="kcard dcard" draggable="true" data-id="{d.id}"><a href="{u("deal", did=d.id)}">{escape(d.name)}</a>'
                f'<div class="small muted">{escape(d.sponsor or "")} · {escape(d.asset_class or "")}</div>'
                f'<div style="justify-content:space-between;margin-top:6px">{sbadge(score(d, w))}<span class="small">${(d.check_size or 0) / 1e6:.1f}M</span></div></div>'
                for d in cols[s]) + "</div>" for s in DEAL_STAGES) + "</div>"
        js = ("<style>.dcard{display:block!important;cursor:grab}.dcard>a{display:block;font-weight:600;color:var(--ink)}.dcard>div:last-child{display:flex!important}"
              ".kcol.over{outline:2px dashed var(--accent)}</style><script>document.addEventListener('DOMContentLoaded',function(){var tok=JSON.parse(document.body.getAttribute('hx-headers'))['X-CSRFToken'];"
              "document.querySelectorAll('.dcard').forEach(function(c){c.addEventListener('dragstart',function(e){e.dataTransfer.setData('text',c.dataset.id)})});"
              "document.querySelectorAll('.kcol').forEach(function(col){col.addEventListener('dragover',function(e){e.preventDefault();col.classList.add('over')});"
              "col.addEventListener('dragleave',function(){col.classList.remove('over')});col.addEventListener('drop',function(e){e.preventDefault();var fd=new FormData();"
              "fd.append('stage',col.dataset.status);fd.append('csrf_token',tok);fetch('" + u("deals_list").rsplit("deals/", 1)[0] + "deals/'+e.dataTransfer.getData('text')+'/stage',"
              "{method:'POST',body:fd,headers:{'X-Requested-With':'fetch'}}).then(function(){location.reload()})})})});</script>")
        body = html(h + js)
    return render("Pipeline", [html(bar), body], sub=f"{len(deals)} deals", actions=[("Export CSV", u("deals_export")), ("+ New deal", u("deals_new"), "primary")])


@bp.route("/deals/<int:did>/")
def deal(did):
    d = db.get_or_404(Deal, did)
    w = weights()
    sc = {x.criterion: x for x in d.scores}
    s = score(d, w)
    nxt = [x for x in DEAL_STAGES if x != d.stage]
    stage_btns = " ".join(str(postbtn(u("set_stage", did=d.id), x, "btn sm", f'<input type="hidden" name="stage" value="{x}">')) for x in nxt)
    score_form = form(u("set_scores", did=d.id), [(f"s_{c}", f"{c} (weight {w[c]:g})", "select",
                                                    [("", "—", False)] + [(str(i), str(i), sc.get(c) and sc[c].score == i) for i in range(1, 6)]) for c in CRITERIA], submit="Save scores")
    ov = [kpis([("Score", sbadge(s)), ("Deal size", M(d.size)), ("Our check", M(d.check_size)), ("Target IRR", f"{d.target_irr or 0:.1f}%"),
                ("Target MOIC", f"{d.target_moic or 0:.1f}x"), ("Hold", f"{d.hold_years or 0:g} yrs")]),
          row(card("Thesis", html(f'<div style="padding:14px 16px" class="small"><p>{escape(d.thesis or "—")}</p><p><b>Key risks:</b> {escape(d.risks or "—")}</p>'
                                  f'<p><b>Next step:</b> {escape(d.next_step or "—")}</p>{"<p><b>Pass reason:</b> " + str(escape(d.pass_reason)) + "</p>" if d.pass_reason else ""}</div>')),
              card("Details", table(["Field", "Value"], [["Sponsor", d.sponsor or "—"], ["Asset class", d.asset_class], ["Sector", d.sector], ["Location", d.location],
                                                         ["Source", d.source], ["Owner", d.owner.name if d.owner else "—"], ["Received", D(d.received)],
                                                         ["Decision", D(d.decision_date)], ["Ledger investment", link(d.investment.name, url_for("family_office.investments_edit", obj_id=d.investment_id))
                                                                                            if d.investment else "—"]], sortable=False))),
          card("Move stage", html(f'<div style="padding:12px 16px;display:flex;gap:6px;flex-wrap:wrap">{stage_btns}</div>'))]
    scoring = [row(card("Scorecard", score_form, flush=False),
                   card("Breakdown", table(["Criterion", ">Weight", ">Score"], [[c, f"{w[c]:g}", sc[c].score if c in sc else "—"] for c in CRITERIA], foot=["Weighted", "", sbadge(s)],
                                           sortable=False)))]
    fu = [card("Follow-ups", [table(["Note", "Owner", "Due", ""], [[f.note, f.owner.name if f.owner else "—", D(f.due),
                                                                   status("Done") if f.done else postbtn(u("followup_done", fid=f.id), "Done")] for f in d.followups], empty="None."),
                              form(u("add_followup", did=d.id), [("note", "New follow-up", "text", ""), ("due", "Due", "date", (date.today() + timedelta(days=7)).isoformat())],
                                   submit="Add")], flush=False)]
    act = [card("Activity", [lst([(a.text, f"{a.user.name if a.user else '—'} · {a.at:%b %d, %Y %H:%M}") for a in d.activity]),
                             form(u("add_note", did=d.id), [("text", "Add a note", "textarea", "")], submit="Add note")], flush=False)]
    actions = [("Edit", u("deals_edit", obj_id=d.id))]
    if d.stage in ("Approved", "Closed") and not d.investment_id:
        actions.append(("post", "Book as investment", u("convert", did=d.id), "primary", "Create a ledger investment for this deal?"))
    return render(d.name, [tabs([("overview", "Overview", ov), ("score", "Scoring", scoring), ("followups", f"Follow-ups ({len([f for f in d.followups if not f.done])})", fu),
                                 ("activity", "Activity", act)])],
                  sub=Markup(f"{escape(d.sponsor or '')} · ") + pill(d.stage, STAGE_TONE[d.stage]), back=("Pipeline", u("pipeline")), active="deals.pipeline", actions=actions)


@bp.route("/deals/<int:did>/stage", methods=["POST"])
@write_required
def set_stage(did):
    d = db.get_or_404(Deal, did)
    new = request.form.get("stage")
    if new not in DEAL_STAGES:
        abort(400)
    if new == "IC Review":
        s = score(d)
        mn = st.get("deals", "min_score_ic", 3.2, float)
        if s is None or s < mn:
            msg = f"Score {s if s is not None else 'missing'} is below the {mn:g} needed for IC."
            if request.headers.get("X-Requested-With") == "fetch":
                flash(msg, "error")
                return ("blocked", 409)
            flash(msg, "error")
            return redirect(u("deal", did=d.id, tab="score"))
    if new in ("Approved", "Passed") and not current_user.is_admin:
        abort(403)
    old, d.stage = d.stage, new
    if new in ("Approved", "Passed", "Closed"):
        d.decision_date = date.today()
    log(d, f"Moved from {old} to {new}.")
    audit("deals", "stage", "deal", d.id, f"{d.name}: {old} → {new}")
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return ("ok", 200)
    flash(f"{d.name} moved to {new}.", "success")
    return redirect(u("deal", did=d.id))


@bp.route("/deals/<int:did>/scores", methods=["POST"])
@write_required
def set_scores(did):
    d = db.get_or_404(Deal, did)
    have = {x.criterion: x for x in d.scores}
    for c in CRITERIA:
        v = request.form.get(f"s_{c}")
        if v:
            x = have.get(c) or DealScore(deal_id=d.id, criterion=c)
            x.score = int(v)
            db.session.add(x)
    db.session.flush()
    db.session.refresh(d)
    log(d, f"Scorecard updated (score {score(d)}).")
    audit("deals", "score", "deal", d.id, f"{d.name} → {score(d)}")
    db.session.commit()
    flash("Scores saved.", "success")
    return redirect(u("deal", did=d.id, tab="score"))


@bp.route("/deals/<int:did>/followup", methods=["POST"])
@write_required
def add_followup(did):
    d = db.get_or_404(Deal, did)
    note_ = (request.form.get("note") or "").strip()
    if note_:
        due = request.form.get("due")
        db.session.add(FollowUp(deal_id=d.id, owner_id=current_user.id, note=note_, due=date.fromisoformat(due) if due else None))
        log(d, f"Follow-up added: {note_}")
        db.session.commit()
    return redirect(u("deal", did=d.id, tab="followups"))


@bp.route("/followups/<int:fid>/done", methods=["POST"])
@write_required
def followup_done(fid):
    f = db.get_or_404(FollowUp, fid)
    f.done = True
    log(f.deal, f"Follow-up done: {f.note}")
    db.session.commit()
    return redirect(request.referrer or u("followups"))


@bp.route("/deals/<int:did>/note", methods=["POST"])
@write_required
def add_note(did):
    d = db.get_or_404(Deal, did)
    t = (request.form.get("text") or "").strip()
    if t:
        log(d, t[:400])
        db.session.commit()
    return redirect(u("deal", did=d.id, tab="activity"))


@bp.route("/deals/<int:did>/convert", methods=["POST"])
@write_required
def convert(did):
    d = db.get_or_404(Deal, did)
    if d.stage not in ("Approved", "Closed") or d.investment_id:
        abort(400)
    ent = Entity.query.filter(Entity.name.ilike("%Ventures%" if d.asset_class == "Venture Capital" else "%Real Estate%" if d.asset_class == "Real Estate" else "%Growth%")).first()
    inv = Investment(name=d.name, entity_id=ent.id if ent else None, asset_class=d.asset_class, deal_type="Direct", sponsor=d.sponsor, sector=d.sector,
                     vintage=date.today().year, commitment=d.check_size, invested=0, fmv=0, distributions=0, status="Active", target_irr=d.target_irr,
                     target_moic=d.target_moic, hold_years=d.hold_years, last_mark=date.today())
    db.session.add(inv)
    db.session.flush()
    d.investment_id = inv.id
    d.stage = "Closed"
    log(d, f"Booked as a ledger investment (commitment ${d.check_size or 0:,.0f}).")
    audit("deals", "convert", "deal", d.id, f"{d.name} → investment {inv.id}")
    db.session.commit()
    flash(f"{d.name} is now in Family Office › Investments.", "success")
    return redirect(u("deal", did=d.id))


@bp.route("/compare/")
def compare():
    w = weights()
    ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip().isdigit()][:5]
    deals = [db.session.get(Deal, i) for i in ids]
    deals = [d for d in deals if d]
    opts = Deal.query.filter(Deal.stage.in_(OPEN + ["Approved"])).order_by(Deal.name).all()
    picker = ('<form method="get" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center" onsubmit="var v=[].slice.call(this.querySelectorAll(\'input:checked\')).map(function(x){return x.value});'
              'this.ids.value=v.join(\',\')"><input type="hidden" name="ids">' + "".join(
                  f'<label class="chip"><input type="checkbox" value="{d.id}" {"checked" if d.id in ids else ""}> {escape(d.name)}</label>' for d in opts)
              + '<button class="btn primary sm">Compare</button></form>')
    blocks = [card("Pick up to five deals", html(f'<div style="padding:12px 16px">{picker}</div>'))]
    if deals:
        sc = {d.id: {x.criterion: x.score for x in d.scores} for d in deals}
        rows = [["Stage"] + [pill(d.stage, STAGE_TONE[d.stage]) for d in deals], ["Weighted score"] + [sbadge(score(d, w)) for d in deals],
                ["Sponsor"] + [d.sponsor for d in deals], ["Asset class"] + [d.asset_class for d in deals], ["Deal size"] + [M(d.size) for d in deals],
                ["Our check"] + [M(d.check_size) for d in deals], ["Target IRR"] + [f"{d.target_irr or 0:.1f}%" for d in deals],
                ["Target MOIC"] + [f"{d.target_moic or 0:.1f}x" for d in deals], ["Hold"] + [f"{d.hold_years or 0:g} yrs" for d in deals]]
        rows += [[c] + [sc[d.id].get(c, "—") for d in deals] for c in CRITERIA]
        rows += [["Key risks"] + [d.risks for d in deals]]
        blocks.append(card("Side by side", table([""] + [d.name for d in deals], rows, sortable=False)))
        blocks.append(card("Scores", chart(dict(type="bar", money=False, data=dict(labels=CRITERIA, datasets=[dict(label=d.name, data=[sc[d.id].get(c, 0) for c in CRITERIA])
                                                                                                            for d in deals])), 260)))
    return render("Compare", blocks)


@bp.route("/follow-ups/")
def followups():
    show = request.args.get("show", "open")
    q = FollowUp.query
    if show == "open":
        q = q.filter_by(done=False)
    elif show == "mine":
        q = q.filter_by(done=False, owner_id=current_user.id)
    fus = q.order_by(FollowUp.due).all()
    chips = "".join(f'<a class="chip {"on" if show == x else ""}" href="{u("followups", show=x)}">{x.title()}</a>' for x in ["open", "mine", "all"])
    return render("Follow-ups", [html(f'<div class="chips">{chips}</div>'),
                                 card(None, table(["Due", "Deal", "Follow-up", "Owner", ""], [[Markup(f'<span class="{"neg" if f.due and f.due < date.today() and not f.done else ""}">{D(f.due)}</span>'),
                                                                                             dlink(f.deal), f.note, f.owner.name if f.owner else "—",
                                                                                             status("Done") if f.done else postbtn(u("followup_done", fid=f.id), "Mark done")]
                                                                                            for f in fus], empty="No follow-ups."))],
                  actions=[("+ New follow-up", u("followup_records_new"), "primary")])


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    r = st.handle("deals", SETTINGS)
    if r:
        return r
    return render("Settings", [card("Scoring weights and rules", form(u("settings"), st.form_fields("deals", SETTINGS)), flush=False,
                                    sub="Weights change every deal's weighted score immediately.")])

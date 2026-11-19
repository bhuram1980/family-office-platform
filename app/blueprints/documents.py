"""Documents: an inbox that proposes where each file belongs and files it on approval, plus e-signatures, requests and hiring paperwork."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Response, abort, flash, redirect, request, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from ..crud import Field as F, Resource
from ..extensions import db
from ..models import (AgentRun, AuditLog, CapitalCall, Candidate, Deal, Distribution, DocRequest, Document, Entity, InboundEmail, Investment, PEDocument,
                      Property, SignatureRequest, Signer, User)
from ..models.documents import DOC_KINDS
from ..pages import D, M, b, bar_chart, card, chart, donut, form, html, kpis, link, lst, note, pill, render, row, status, table, tabs
from ..services import settings as st
from ..services.audit import audit
from ..services.classify import classify
from ..services.pdf import make_pdf
from .common import make_bp, write_required

bp = make_bp("documents", "documents")
SETTINGS = [("auto_file_threshold", "Auto-file when confidence is at least", "0.9", "number"), ("retention_days", "Keep deleted documents for (days)", "30", "number"),
            ("intake_address", "Intake email address", "docs@alladin-fo.example"), ("dropbox_root", "Watched Dropbox folder", "/Alladin FO/Inbox")]
APP_LABEL = {"pevc": "PE / VC", "family-office": "Family Office", "real-estate": "Real Estate", "stocks": "Stocks", "deals": "Deals", "documents": "Documents"}


def u(ep, **kw):
    return url_for(f"documents.{ep}", **kw)


def _csrf():
    from flask import session
    import secrets
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def postbtn(action, label, cls="btn sm", extra=""):
    return Markup(f'<form method="post" action="{action}" style="display:inline"><input type="hidden" name="csrf_token" value="{_csrf()}">{extra}'
                  f'<button class="{cls}">{escape(label)}</button></form>')


def live():
    return Document.query.filter(Document.deleted_at.is_(None))


def dlink(d):
    return link(d.filename, u("doc", did=d.id), "tk")


def conf(c):
    if c is None:
        return "—"
    return pill(f"{c * 100:.0f}%", "green" if c >= 0.8 else "amber" if c >= 0.6 else "red")


def target_label(d):
    t = d.target
    return t.name if t else "—"


def apply_classification(d):
    c = classify(d.filename, d.text or "")
    d.proposed_kind, d.proposed_app, d.confidence = c["kind"], c["app"], c["confidence"]
    d.period, d.amount = d.period or c["period"], d.amount or c["amount"]
    d.investment_id = d.property_id = d.deal_id = d.entity_id = None
    if c["target"]:
        setattr(d, f"{c['target'][0]}_id", c["target"][1].id)


def file_doc(d, user_id=None):
    """File a document and post its side effects into the owning app."""
    d.kind = d.kind or d.proposed_kind
    d.status = "Filed"
    d.filed_at = datetime.utcnow()
    d.filed_by_id = user_id
    effects = []
    inv = d.investment
    if inv and d.kind == "Capital call" and d.amount:
        if not CapitalCall.query.filter_by(investment_id=inv.id, amount=d.amount).first():
            db.session.add(CapitalCall(investment_id=inv.id, notice_date=date.today(), due=date.today() + timedelta(days=10), amount=d.amount, status="Pending"))
            effects.append(f"capital call ${d.amount:,.0f} added to {inv.name}")
    if inv and d.kind == "Distribution notice" and d.amount:
        db.session.add(Distribution(investment_id=inv.id, day=date.today(), amount=d.amount, kind="Income", tied_out=False))
        inv.distributions = (inv.distributions or 0) + d.amount
        effects.append(f"distribution ${d.amount:,.0f} recorded on {inv.name}")
    if inv and d.kind in ("Quarterly statement", "Capital account") and d.period:
        if not PEDocument.query.filter_by(investment_id=inv.id, period=d.period, kind=d.kind).first():
            db.session.add(PEDocument(investment_id=inv.id, period=d.period, kind=d.kind, received=date.today(), filename=d.filename))
            effects.append(f"{d.period} {d.kind.lower()} marked received in PE / VC coverage")
    if d.email:
        d.email.processed = all(a.status != "Inbox" for a in d.email.attachments)
    return effects


Resource("documents", "requests", DocRequest, "Tracker", [
    F("what", "Document", required=True), F("from_party", "From"), F("owner_id", "Owner", type="fk", fk=User, fk_label=lambda x: x.name),
    F("requested_on", type="date"), F("due", type="date"), F("status", type="select", choices=["Requested", "Received", "Overdue", "Canceled"]),
], singular="Request", order_by=DocRequest.due, filters=["status"], nav="documents.tracker").register(bp)

Resource("documents", "candidates", Candidate, "Hiring", [
    F("name", required=True), F("role"), F("stage", type="select", choices=["Screen", "Interview", "Offer", "Hired", "Declined"]), F("resume", "Résumé", type="bool"),
    F("offer_letter", "Offer letter", type="select", choices=["—", "Draft", "Sent", "Signed"]),
    F("background_check", "Background check", type="select", choices=["—", "In progress", "Clear", "Flagged"]), F("i9", "I-9 on file", type="bool"),
    F("start_date", type="date"),
], singular="Candidate", order_by=Candidate.id, filters=["stage"], nav="documents.hiring").register(bp)


UPLOAD = """<form method="post" action="{action}" enctype="multipart/form-data" style="display:flex;gap:8px;align-items:center;padding:12px 16px">
<input type="hidden" name="csrf_token" value="{tok}"><input type="file" name="files" multiple required class="inp" style="flex:1">
<button class="btn primary">Upload to inbox</button></form>"""


@bp.route("/")
def dashboard():
    return inbox()


@bp.route("/inbox/")
def inbox():
    docs = live().filter_by(status="Inbox").order_by(Document.received_at.desc()).all()
    thr = st.get("documents", "auto_file_threshold", 0.9, float)
    filed7 = live().filter(Document.status == "Filed", Document.filed_at >= datetime.utcnow() - timedelta(days=7)).count()
    rows = [[dlink(d), d.source, pill(d.proposed_kind or "—", "blue"), target_label(d), APP_LABEL.get(d.proposed_app, d.proposed_app or "—"), conf(d.confidence),
             Markup('<span class="neg">⚑</span>') if d.flagged else "", d.received_at.strftime("%b %d"),
             postbtn(u("approve", did=d.id), "File", "btn sm green") + Markup(" ") + link("Review", u("doc", did=d.id), "btn sm")] for d in docs]
    return render("Inbox", [
        kpis([("Waiting", len(docs), "to review", "warn" if docs else "", "#4f46e5"), ("High confidence", len([d for d in docs if (d.confidence or 0) >= thr]), f"≥ {thr * 100:.0f}%", "", "#10b981"),
              ("Flagged", len([d for d in docs if d.flagged]), "", "neg", "#ef4444"), ("Filed this week", filed7, "", "pos", "#0ea5e9")]),
        card("Upload", html(UPLOAD.format(action=u("upload"), tok=_csrf()))),
        card(None, table(["Document", "Source", "Proposed type", "Belongs to", "App", ">Confidence", "", "Received", ""], rows, empty="Inbox zero.")),
    ], sub="Each file gets a proposed type and owner. File it as proposed, or open it to change the proposal.", active="documents.inbox",
        actions=[("post", f"File all ≥ {thr * 100:.0f}%", u("approve_confident"), "primary", None)])


@bp.route("/upload", methods=["POST"])
@write_required
def upload():
    n = 0
    for f in request.files.getlist("files"):
        if not f or not f.filename:
            continue
        data = f.read()
        text = ""
        if (f.mimetype or "").startswith("text/"):
            text = data[:20000].decode("utf-8", "replace")
        elif data.startswith(b"%PDF"):
            import re as _re
            text = " ".join(x.decode("latin-1") for x in _re.findall(rb"\(([^)]{3,200})\)\s*Tj", data[:400000]))
        d = Document(filename=f.filename[:255], mime=f.mimetype, size=len(data), content=data, text=text, source="Upload", received_at=datetime.utcnow())
        apply_classification(d)
        db.session.add(d)
        db.session.flush()
        audit("documents", "upload", "document", d.id, d.filename)
        n += 1
    db.session.commit()
    flash(f"Uploaded {n} file(s); proposals are ready.", "success")
    return redirect(u("inbox"))


@bp.route("/documents/<int:did>/")
def doc(did):
    d = db.get_or_404(Document, did)
    sel = lambda objs, cur: [("", "—", False)] + [(o.id, o.name, o.id == cur) for o in objs]
    frm = form(u("save", did=d.id), [
        ("kind", "Type", "select", [(k, k, k == (d.kind or d.proposed_kind)) for k in DOC_KINDS]),
        ("investment_id", "Investment", "select", sel(Investment.query.order_by(Investment.name).all(), d.investment_id)),
        ("property_id", "Property", "select", sel(Property.query.order_by(Property.name).all(), d.property_id)),
        ("deal_id", "Deal", "select", sel(Deal.query.order_by(Deal.name).all(), d.deal_id)),
        ("entity_id", "Entity", "select", sel(Entity.query.order_by(Entity.name).all(), d.entity_id)),
        ("period", "Period (e.g. 2026Q3)", "text", d.period or ""), ("amount", "Amount", "number", d.amount),
        ("action", "", "select", [("save", "Save only", False), ("file", "Save and file", d.status == "Inbox")])], submit="Apply")
    preview = (f'<iframe src="{u("download", did=d.id, inline=1)}" style="width:100%;height:560px;border:0;border-radius:8px"></iframe>'
               if d.mime == "application/pdf" else f'<pre style="white-space:pre-wrap;padding:14px" class="small">{escape((d.text or "")[:4000])}</pre>')
    hist = AuditLog.query.filter_by(app="documents", entity="document", entity_id=d.id).order_by(AuditLog.at.desc()).all()
    actions = [("Download", u("download", did=d.id))]
    if d.deleted_at:
        actions.append(("post", "Restore", u("restore", did=d.id), "primary", None))
    else:
        if d.status == "Inbox":
            actions.append(("post", "Reject", u("reject", did=d.id), "", "Reject this document?"))
        actions.append(("post", "Unflag" if d.flagged else "Flag", u("flag", did=d.id), "", None))
        actions.append(("post", "Delete", u("delete", did=d.id), "", "Move to recovery?"))
    return render(d.filename, [
        row(card("Preview", html(preview), flush=False),
            [card("Proposal", table(["", ""], [["Status", status(d.status)], ["Proposed type", d.proposed_kind or "—"], ["Belongs to", target_label(d)],
                                              ["App", APP_LABEL.get(d.proposed_app, "—")], ["Confidence", conf(d.confidence)], ["Source", f"{d.source} {d.folder or ''}"],
                                              ["Received", d.received_at.strftime("%b %d, %Y %H:%M")], ["Size", f"{(d.size or 0) / 1024:.1f} KB"],
                                              ["Flag", d.flag_reason or "—"], ["Filed", f"{d.filed_by.name} · {d.filed_at:%b %d}" if d.filed_by else "—"]], sortable=False)),
             card("Classify and file", frm, flush=False),
             card("History", lst([(a.action.title(), f"{a.user.name if a.user else 'system'} · {a.at:%b %d %H:%M} · {a.detail or ''}") for a in hist], empty="No history."))]),
    ], back=("Inbox", u("inbox")), active="documents.inbox", actions=actions)


@bp.route("/documents/<int:did>/download")
def download(did):
    d = db.get_or_404(Document, did)
    data = db.session.query(Document.content).filter_by(id=d.id).scalar() or b""
    disp = "inline" if request.args.get("inline") else "attachment"
    safe = d.filename.replace('"', "").encode("ascii", "replace").decode()
    return Response(data, mimetype=d.mime or "application/octet-stream", headers={"Content-Disposition": f'{disp}; filename="{safe}"',
                                                                                    "X-Content-Type-Options": "nosniff"})


@bp.route("/documents/<int:did>/save", methods=["POST"])
@write_required
def save(did):
    d = db.get_or_404(Document, did)
    k = request.form.get("kind")
    if k in DOC_KINDS:
        d.kind = d.proposed_kind = k
    for f in ("investment_id", "property_id", "deal_id", "entity_id"):
        v = request.form.get(f)
        setattr(d, f, int(v) if v else None)
    d.period = request.form.get("period") or None
    a = request.form.get("amount")
    d.amount = float(a) if a else None
    msg = "saved"
    if request.form.get("action") == "file":
        eff = file_doc(d, current_user.id)
        msg = "filed" + (f" — {'; '.join(eff)}" if eff else "")
    audit("documents", "file" if "filed" in msg else "update", "document", d.id, msg)
    db.session.commit()
    flash(f"{d.filename} {msg}.", "success")
    return redirect(u("inbox") if d.status == "Filed" else u("doc", did=d.id))


@bp.route("/documents/<int:did>/approve", methods=["POST"])
@write_required
def approve(did):
    d = db.get_or_404(Document, did)
    eff = file_doc(d, current_user.id)
    audit("documents", "file", "document", d.id, "; ".join(eff) or f"filed as {d.kind}")
    db.session.commit()
    flash(f"Filed {d.filename} as {d.kind}" + (f" — {'; '.join(eff)}" if eff else "") + ".", "success")
    return redirect(request.referrer or u("inbox"))


@bp.route("/approve-confident", methods=["POST"])
@write_required
def approve_confident():
    thr = st.get("documents", "auto_file_threshold", 0.9, float)
    n = 0
    for d in live().filter(Document.status == "Inbox", Document.confidence >= thr, Document.flagged.is_(False)).all():
        file_doc(d, current_user.id)
        audit("documents", "file", "document", d.id, "bulk approve")
        n += 1
    db.session.commit()
    flash(f"Filed {n} document(s).", "success")
    return redirect(u("inbox"))


def _simple(action_name, fn):
    def view(did):
        d = db.get_or_404(Document, did)
        msg = fn(d)
        audit("documents", action_name, "document", d.id, msg)
        db.session.commit()
        flash(msg, "success")
        return redirect(u("doc", did=d.id) if action_name not in ("delete",) else u("inbox"))
    view.__name__ = action_name
    return write_required(view)


def _reject(d):
    d.status = "Rejected"
    return f"{d.filename} rejected."


def _flag(d):
    d.flagged = not d.flagged
    d.flag_reason = (request.form.get("reason") or "Flagged for review") if d.flagged else None
    return f"{d.filename} {'flagged' if d.flagged else 'unflagged'}."


def _delete(d):
    d.deleted_at = datetime.utcnow()
    return f"{d.filename} moved to recovery."


def _restore(d):
    d.deleted_at = None
    if d.status == "Rejected":
        d.status = "Inbox"
    return f"{d.filename} restored."


for _n, _f in (("reject", _reject), ("flag", _flag), ("delete", _delete), ("restore", _restore)):
    bp.add_url_rule(f"/documents/<int:did>/{_n}", _n, _simple(_n, _f), methods=["POST"])


@bp.route("/documents/<int:did>/purge", methods=["POST"])
@write_required
def purge(did):
    if not current_user.is_admin:
        abort(403)
    d = db.get_or_404(Document, did)
    audit("documents", "purge", "document", d.id, d.filename)
    db.session.delete(d)
    db.session.commit()
    flash("Permanently deleted.", "success")
    return redirect(u("recovery"))


def _doc_table(docs, extra=None):
    return table(["Document", "Type", "Belongs to", "Source", "Status", "Received"] + ([extra[0]] if extra else []),
                 [[dlink(d), d.kind or d.proposed_kind, target_label(d), d.source, status(d.status), d.received_at.strftime("%b %d, %Y")] + ([extra[1](d)] if extra else [])
                  for d in docs], empty="No documents.")


@bp.route("/dropbox/")
def dropbox():
    docs = live().filter_by(source="Dropbox").order_by(Document.received_at.desc()).all()
    by = defaultdict(list)
    for d in docs:
        by[d.folder or "/"].append(d)
    blocks = [note(f"Watching {st.get('documents', 'dropbox_root', '/Alladin FO/Inbox')} and its sub-folders. New files land in the Inbox with a proposal.")]
    for f, ds in sorted(by.items()):
        blocks.append(card(f"{f} · {len(ds)}", _doc_table(ds)))
    return render("Dropbox", blocks, actions=[("post", "Sync now", u("sync"), "primary", None)])


@bp.route("/dropbox/sync", methods=["POST"])
@write_required
def sync():
    """Simulated folder sync: picks up one new statement from a watched folder."""
    inv = Investment.query.filter(Investment.asset_class.in_(["Private Equity", "Venture Capital"]), Investment.status == "Active").order_by(db.func.random()).first()
    q = f"{date.today().year}Q{max(1, (date.today().month - 1) // 3)}"
    name = f"{inv.name.split(' — ')[0]} quarterly statement {q}.pdf"
    pdf = make_pdf("Quarterly Statement", [f"{inv.name}", "Net asset value as of quarter end.", f"Ending capital $ {inv.fmv or 0:,.0f}."])
    d = Document(filename=name, mime="application/pdf", size=len(pdf), content=pdf, text=f"Quarterly Statement {inv.name} {q}", source="Dropbox",
                 folder="/GP Portals/Statements", received_at=datetime.utcnow())
    apply_classification(d)
    db.session.add(d)
    db.session.add(AgentRun(agent="Dropbox sync", processed=1, filed=0, note=name))
    db.session.flush()
    audit("documents", "sync", "document", d.id, name)
    db.session.commit()
    flash(f"Picked up {name}.", "success")
    return redirect(u("inbox"))


@bp.route("/emails/")
def emails():
    es = InboundEmail.query.order_by(InboundEmail.received_at.desc()).all()
    rows = [[e.received_at.strftime("%b %d %H:%M"), e.from_addr, link(e.subject, u("email", eid=e.id)), len(e.attachments),
             status("Done") if e.processed else status("Pending")] for e in es]
    return render("Emails", [note(f"Forward documents to {st.get('documents', 'intake_address', 'docs@alladin-fo.example')}; attachments are split out into the Inbox."),
                             card(None, table(["Received", "From", "Subject", ">Attachments", "Status"], rows))])


@bp.route("/emails/<int:eid>/")
def email(eid):
    e = db.get_or_404(InboundEmail, eid)
    return render(e.subject, [card("Message", html(f'<div style="padding:14px 16px" class="small"><b>From:</b> {escape(e.from_addr)}<br><b>Received:</b> {e.received_at:%b %d, %Y %H:%M}'
                                                   f'<p style="white-space:pre-wrap">{escape(e.body or "")}</p></div>')),
                              card("Attachments", _doc_table(e.attachments))], back=("Emails", u("emails")), active="documents.emails")


@bp.route("/attachments/")
def attachments():
    docs = live().filter(Document.email_id.isnot(None)).order_by(Document.received_at.desc()).all()
    return render("Attachments", [card(None, _doc_table(docs, ("Email", lambda d: link(d.email.subject[:50], u("email", eid=d.email_id)))))])


@bp.route("/coverage/")
def coverage():
    kinds = ["Quarterly statement", "Capital account", "K-1", "Capital call", "Distribution notice"]
    invs = Investment.query.filter(Investment.asset_class.in_(["Private Equity", "Venture Capital", "Private Credit"]), Investment.status == "Active").order_by(Investment.name).all()
    cnt = defaultdict(int)
    for d in live().filter(Document.status == "Filed", Document.investment_id.isnot(None)).all():
        cnt[(d.investment_id, d.kind)] += 1
    rows = [[link(i.name, url_for("pevc.position", iid=i.id))] + [pill(str(cnt[(i.id, k)]), "green") if cnt[(i.id, k)] else pill("0", "red" if k == "Quarterly statement" else "gray")
                                                                   for k in kinds] for i in invs]
    props = Property.query.all()
    pc = defaultdict(int)
    for d in live().filter(Document.status == "Filed", Document.property_id.isnot(None)).all():
        pc[d.property_id] += 1
    return render("Coverage", [
        kpis([("Investments with no filed statement", len([i for i in invs if not cnt[(i.id, 'Quarterly statement')]]), "", "neg"),
              ("Properties with no reports", len([p for p in props if not pc[p.id]]), "", "warn")]),
        card("Filed documents by investment and type", table(["Investment"] + kinds, rows, sortable=False)),
        card("Property reports", table(["Property", ">Filed reports"], [[p.name, pc[p.id]] for p in props])),
    ], actions=[("PE / VC coverage →", url_for("pevc.coverage"))])


@bp.route("/recovery/")
def recovery():
    dele = Document.query.filter(Document.deleted_at.isnot(None)).order_by(Document.deleted_at.desc()).all()
    rej = live().filter_by(status="Rejected").all()
    btns = lambda d: postbtn(u("restore", did=d.id), "Restore") + Markup(" ") + postbtn(u("purge", did=d.id), "Delete forever", "btn sm red")
    return render("Recovery", [note(f"Deleted documents are kept for {st.get('documents', 'retention_days', 30, float):.0f} days."),
                               card(f"Deleted · {len(dele)}", _doc_table(dele, ("", btns))), card(f"Rejected · {len(rej)}", _doc_table(rej, ("", lambda d: postbtn(u("restore", did=d.id), "Back to inbox"))))])


@bp.route("/deals/")
def deals():
    docs = live().filter(Document.deal_id.isnot(None)).order_by(Document.received_at.desc()).all()
    by = defaultdict(list)
    for d in docs:
        by[d.deal].append(d)
    blocks = [card(f"{dl.name} · {len(ds)}", _doc_table(ds), right=("Open deal →", url_for("deals.deal", did=dl.id))) for dl, ds in sorted(by.items(), key=lambda x: x[0].name)]
    return render("Deal Documents", blocks or [note("No deal documents yet.")])


@bp.route("/tracker/")
def tracker():
    rs = DocRequest.query.order_by(DocRequest.due).all()
    for r in rs:
        if r.status == "Requested" and r.due and r.due < date.today():
            r.status = "Overdue"
    db.session.commit()
    rows = [[link(r.what, u("requests_edit", obj_id=r.id)), r.from_party, r.owner.name if r.owner else "—", D(r.requested_on), D(r.due), status(r.status),
             postbtn(u("request_received", rid=r.id), "Mark received") if r.status in ("Requested", "Overdue") else ""] for r in rs]
    return render("Tracker", [kpis([("Open requests", len([r for r in rs if r.status in ("Requested", "Overdue")])), ("Overdue", len([r for r in rs if r.status == "Overdue"]), "", "neg"),
                                    ("Received", len([r for r in rs if r.status == "Received"]), "", "pos")]),
                              card(None, table(["Document", "From", "Owner", "Requested", "Due", "Status", ""], rows))],
                  actions=[("+ New request", u("requests_new"), "primary")])


@bp.route("/tracker/<int:rid>/received", methods=["POST"])
@write_required
def request_received(rid):
    r = db.get_or_404(DocRequest, rid)
    r.status = "Received"
    audit("documents", "received", "doc_request", r.id, r.what)
    db.session.commit()
    return redirect(u("tracker"))


@bp.route("/flags/")
def flags():
    docs = live().filter_by(flagged=True).order_by(Document.received_at.desc()).all()
    return render("Flags", [card(None, _doc_table(docs, ("Reason", lambda d: Markup(f'<span class="neg">{escape(d.flag_reason or "")}</span> ') + postbtn(u("flag", did=d.id), "Clear"))))],
                  sub="Documents that need a second look before anyone acts on them")


# ---------------------------------------------------------------- e-signatures
@bp.route("/e-signatures/")
def esign():
    rs = SignatureRequest.query.order_by(SignatureRequest.created_at.desc()).all()
    rows = [[link(r.title, u("esign_detail", rid=r.id)), status(r.status), ", ".join(f"{s.name} ({s.status})" for s in r.signers),
             D(r.sent_at), D(r.completed_at)] for r in rs]
    by = defaultdict(int)
    for r in rs:
        by[r.status] += 1
    return render("E-Signatures", [kpis([(k, by[k]) for k in ["Draft", "Sent", "Signed", "Declined"]]),
                                   card(None, table(["Envelope", "Status", "Signers", "Sent", "Completed"], rows))],
                  actions=[("+ New envelope", u("esign_new"), "primary")])


@bp.route("/e-signatures/new", methods=["GET", "POST"])
def esign_new():
    if request.method == "POST":
        if not current_user.can_write:
            abort(403)
        r = SignatureRequest(title=request.form["title"].strip() or "Untitled", created_by_id=current_user.id, status="Draft", message=request.form.get("message"))
        did = request.form.get("document_id")
        r.document_id = int(did) if did else None
        db.session.add(r)
        db.session.flush()
        for i in range(1, 4):
            nm, em = request.form.get(f"name{i}", "").strip(), request.form.get(f"email{i}", "").strip()
            if nm:
                db.session.add(Signer(request_id=r.id, name=nm, email=em, order=i))
        audit("documents", "create", "signature_request", r.id, r.title)
        db.session.commit()
        return redirect(u("esign_detail", rid=r.id))
    docs = live().filter_by(status="Filed").order_by(Document.received_at.desc()).limit(80).all()
    return render("New envelope", [card(None, form(u("esign_new"), [("title", "Title", "text", ""), ("document_id", "Document", "select", [("", "—")] + [(d.id, d.filename) for d in docs]),
                                                                    ("message", "Message", "textarea", "Please review and sign."), ("name1", "Signer 1 name", "text", ""),
                                                                    ("email1", "Signer 1 email", "email", ""), ("name2", "Signer 2 name", "text", ""), ("email2", "Signer 2 email", "email", ""),
                                                                    ("name3", "Signer 3 name", "text", ""), ("email3", "Signer 3 email", "email", "")], submit="Create draft"), flush=False)],
                  back=("E-Signatures", u("esign")), active="documents.esign")


@bp.route("/e-signatures/<int:rid>/")
def esign_detail(rid):
    r = db.get_or_404(SignatureRequest, rid)
    rows = [[s.order, s.name, s.email, status(s.status), D(s.signed_at),
             (postbtn(u("esign_action", rid=r.id, action="sign"), "Record signature", "btn sm green", f'<input type="hidden" name="sid" value="{s.id}">') + Markup(" ") +
              postbtn(u("esign_action", rid=r.id, action="decline"), "Record decline", "btn sm", f'<input type="hidden" name="sid" value="{s.id}">'))
             if r.status == "Sent" and s.status in ("Pending", "Delivered") else ""] for s in r.signers]
    actions = []
    if r.status == "Draft":
        actions.append(("post", "Send for signature", u("esign_action", rid=r.id, action="send"), "primary", None))
    if r.status in ("Draft", "Sent"):
        actions.append(("post", "Void", u("esign_action", rid=r.id, action="void"), "", "Void this envelope?"))
    return render(r.title, [kpis([("Status", status(r.status)), ("Sent", D(r.sent_at)), ("Completed", D(r.completed_at))]),
                            card("Signers (signing order)", table(["#", "Name", "Email", "Status", "Signed", ""], rows, sortable=False)),
                            card("Document", html(f'<div style="padding:12px 16px">{dlink(r.document) if r.document else "No document attached."}</div>'))],
                  back=("E-Signatures", u("esign")), active="documents.esign", actions=actions,
                  sub="Sending is recorded here; signatures are logged by the team when they come back.")


@bp.route("/e-signatures/<int:rid>/<action>", methods=["POST"])
@write_required
def esign_action(rid, action):
    r = db.get_or_404(SignatureRequest, rid)
    if action == "send" and r.status == "Draft":
        if not r.signers:
            flash("Add at least one signer first.", "error")
            return redirect(u("esign_detail", rid=r.id))
        r.status, r.sent_at = "Sent", datetime.utcnow()
        r.signers[0].status = "Delivered"
    elif action in ("sign", "decline") and r.status == "Sent":
        s = db.get_or_404(Signer, int(request.form["sid"]))
        if s.request_id != r.id:
            abort(400)
        pending = [x for x in r.signers if x.status in ("Pending", "Delivered")]
        if pending and pending[0].id != s.id:
            flash(f"{pending[0].name} signs first.", "error")
            return redirect(u("esign_detail", rid=r.id))
        if action == "sign":
            s.status, s.signed_at = "Signed", datetime.utcnow()
            rest = [x for x in r.signers if x.status == "Pending"]
            if rest:
                rest[0].status = "Delivered"
            else:
                r.status, r.completed_at = "Signed", datetime.utcnow()
        else:
            s.status = "Declined"
            r.status, r.completed_at = "Declined", datetime.utcnow()
    elif action == "void" and r.status in ("Draft", "Sent"):
        r.status = "Voided"
    else:
        abort(400)
    audit("documents", action, "signature_request", r.id, f"{r.title} → {r.status}")
    db.session.commit()
    return redirect(u("esign_detail", rid=r.id))


@bp.route("/hiring/")
def hiring():
    cs = Candidate.query.order_by(Candidate.id).all()
    chk = lambda v: pill("✓", "green") if v else pill("—", "gray")
    return render("Hiring", [card(None, table(["Candidate", "Role", "Stage", "Résumé", "Offer letter", "Background", "I-9", "Start"],
                                              [[link(c.name, u("candidates_edit", obj_id=c.id)), c.role, status(c.stage), chk(c.resume), c.offer_letter, c.background_check,
                                                chk(c.i9), D(c.start_date)] for c in cs]))],
                  sub="Paperwork checklist for every open role", actions=[("+ Add candidate", u("candidates_new"), "primary")])


@bp.route("/audit/")
def audit_page():
    logs = AuditLog.query.filter_by(app="documents").order_by(AuditLog.at.desc()).limit(300).all()
    return render("Audit", [card(None, table(["When", "Who", "Action", "Record", "Detail"], [[a.at.strftime("%b %d %H:%M"), a.user.name if a.user else "system", a.action,
                                                                                            f"{a.entity} #{a.entity_id or ''}", a.detail] for a in logs], empty="No activity yet."))])


@bp.route("/agents/")
def agents():
    runs = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(60).all()
    last = {}
    for r in runs:
        last.setdefault(r.agent, r)
    cards = "".join(f'<div class="card" style="padding:14px"><b>{escape(a)}</b><div class="small muted">last run {r.started_at:%b %d %H:%M} UTC</div>'
                    f'<div style="margin-top:8px">{status("Active") if not r.errors else pill("Errors", "red")} <span class="small">{r.processed} processed · {r.filed} filed</span></div></div>'
                    for a, r in last.items())
    return render("Agents", [html(f'<div class="grid g4" style="gap:12px">{cards}</div>'),
                             card("Run history", table(["Started (UTC)", "Agent", ">Processed", ">Filed", ">Errors", "Note"],
                                                       [[r.started_at.strftime("%b %d %H:%M"), r.agent, r.processed, r.filed, r.errors, r.note or ""] for r in runs]))],
                  sub="Rule-based intake jobs that read, classify and file documents",
                  actions=[("post", "Run classifier now", u("run_classifier"), "primary", None)])


@bp.route("/agents/classify", methods=["POST"])
@write_required
def run_classifier():
    thr = st.get("documents", "auto_file_threshold", 0.9, float)
    n = filed = 0
    for d in live().filter_by(status="Inbox").all():
        apply_classification(d)
        n += 1
        if (d.confidence or 0) >= thr and not d.flagged:
            file_doc(d, current_user.id)
            filed += 1
    db.session.add(AgentRun(agent="Classifier", processed=n, filed=filed, note=f"threshold {thr:g}"))
    audit("documents", "run", "classifier", None, f"{n} processed, {filed} filed")
    db.session.commit()
    flash(f"Classifier processed {n} document(s) and filed {filed}.", "success")
    return redirect(u("agents"))


@bp.route("/settings/", methods=["GET", "POST"])
def settings():
    r = st.handle("documents", SETTINGS)
    if r:
        return r
    return render("Settings", [card("Intake and filing", form(u("settings"), st.form_fields("documents", SETTINGS)), flush=False)])

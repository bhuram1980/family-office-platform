"""Python-side page builder: analytic pages are described as a list of blocks
and rendered by templates/generic.html inside the shared shell."""
from flask import render_template, url_for
from markupsafe import Markup, escape

from .filters import money as _money, money_short as _ms, pct as _pct, tone as _tone, dfmt


# ---------------------------------------------------------------- cell helpers
def M(v, dec=0, color=False):
    cls = f' class="{_tone(v)}"' if color else ""
    return Markup(f'<span{cls}>{escape(_money(v, dec))}</span>')


def MS(v):
    return Markup(escape(_ms(v)))


def P(v, dec=1, sign=True, color=True):
    if v is None:
        return "—"
    return Markup(f'<span class="{_tone(v) if color else ""}">{escape(_pct(v, dec, sign))}</span>')


def pill(text, tone="gray"):
    return Markup(f'<span class="pill {tone}">{escape(text)}</span>')


STATUS_TONE = {"Active": "green", "Open": "blue", "Paid": "green", "Approved": "green", "Sent": "green", "Done": "green", "Complete": "green",
               "Received": "green", "Filed": "green", "Closed": "gray", "Sold": "gray", "Pending": "amber", "Draft": "gray", "In progress": "blue",
               "Pending approval": "amber", "Overdue": "red", "Late": "red", "Missing": "red", "Expired": "red", "HIGH": "red", "MEDIUM": "amber",
               "LOW": "blue", "Not started": "gray", "Reconciled": "green", "Unreconciled": "amber", "Written off": "red", "Current": "green",
               "Watch": "amber", "Default": "red", "Signed": "green", "Declined": "red", "Voided": "gray", "Delivered": "blue", "Scheduled": "blue",
               "Extended": "amber", "Due soon": "amber", "Requested": "amber", "Rejected": "red", "Funded": "green", "Identified": "blue"}


def status(text):
    return pill(text, STATUS_TONE.get(text, "gray"))


def link(text, url, cls=""):
    return Markup(f'<a class="{cls}" href="{escape(url)}">{escape(text)}</a>')


def b(text):
    return Markup(f"<b>{escape(text)}</b>")


def small(text):
    return Markup(f'<span class="small muted">{escape(text)}</span>')


def D(v, f="%b %d, %Y"):
    return dfmt(v, f)


# ---------------------------------------------------------------- blocks
def kpis(items, cols=None):
    """items: (label, value, sub=None, tone='', color=None)"""
    norm = []
    for it in items:
        it = list(it) + [None] * (5 - len(it))
        norm.append(dict(label=it[0], value=it[1], sub=it[2], tone=it[3] or "", color=it[4]))
    return dict(type="kpis", items=norm, cols=cols or min(len(norm), 6))


def row(*blocks, cols=None):
    return dict(type="row", blocks=list(blocks), cols=cols or f"g{len(blocks)}")


def card(title, body, right=None, sub=None, flush=None):
    body = body if isinstance(body, list) else [body]
    if flush is None:
        flush = all(isinstance(x, dict) and x.get("type") in ("table", "list") for x in body)
    return dict(type="card", title=title, body=body, right=right, sub=sub, flush=flush)


def table(cols, rows, sortable=True, foot=None, max_height=None, compact=True, empty="Nothing here yet."):
    """cols: list of labels; prefix with '>' for right-aligned."""
    c = [(x[1:], "r") if x.startswith(">") else (x, "") for x in cols]
    return dict(type="table", cols=c, rows=rows, sortable=sortable, foot=foot, max_height=max_height, compact=compact, empty=empty)


def chart(cfg, h=260):
    return dict(type="chart", cfg=cfg, h=h)


def bars(rows, color="#6366f1", money=True):
    return dict(type="bars", rows=rows, color=color, money=money)


def lst(items, empty="Nothing here."):
    """items: (title, sub, right, dot)"""
    norm = []
    for it in items:
        it = list(it) + [None] * (4 - len(it))
        norm.append(dict(title=it[0], sub=it[1], right=it[2], dot=it[3]))
    return dict(type="list", items=norm, empty=empty)


def note(text, tone=""):
    return dict(type="note", text=text, tone=tone)


def html(h):
    return dict(type="html", html=Markup(h))


def tabs(items, key="tab"):
    """items: (slug, label, [blocks])"""
    return dict(type="tabs", key=key, items=[dict(slug=s, label=l, blocks=bl if isinstance(bl, list) else [bl]) for s, l, bl in items])


def form(action, fields, submit="Save", title=None):
    """fields: (name, label, type, options/default)"""
    return dict(type="form", action=action, fields=fields, submit=submit, title=title)


# ---------------------------------------------------------------- charts
def bar_chart(labels, data, label="", money=True, color=None, horizontal=False, colors=None, stacked=None):
    if stacked:
        ds = [dict(label=k, data=v) for k, v in stacked.items()]
        cfg = dict(type="bar", money=money, data=dict(labels=labels, datasets=ds),
                   options=dict(scales=dict(x=dict(stacked=True), y=dict(stacked=True))))
    else:
        d = dict(label=label, data=data)
        if colors:
            d["backgroundColor"] = colors
        elif color:
            d["backgroundColor"] = color
        cfg = dict(type="bar", money=money, data=dict(labels=labels, datasets=[d]))
    if horizontal:
        cfg.setdefault("options", {})["indexAxis"] = "y"
    return cfg


def line_chart(labels, series, money=True, fill=False):
    ds = []
    for k, v in series.items():
        d = dict(label=k, data=v)
        if fill:
            d["fill"] = True
        ds.append(d)
    return dict(type="line", money=money, data=dict(labels=labels, datasets=ds))


def donut(labels, data, money=True):
    return dict(type="doughnut", money=money, data=dict(labels=labels, datasets=[dict(data=data)]))


# ---------------------------------------------------------------- render
def render(title, blocks, sub=None, actions=None, back=None, active=None, topbar=None):
    """actions: (label, url, style) where style in '', 'primary', 'dark' ; or ('post', label, url, style, confirm)"""
    return render_template("generic.html", page_title=title, sub=sub, blocks=blocks, actions=actions or [],
                           back=back, active_nav=active, topbar=topbar)

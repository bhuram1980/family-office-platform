from datetime import datetime, date


def money(v, dec=0):
    if v is None:
        return "—"
    s = f"${abs(v):,.{dec}f}"
    return f"({s})" if v < 0 else s


def money_short(v, dec=1):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e9:
        s = f"${a/1e9:,.{dec}f}B"
    elif a >= 1e6:
        s = f"${a/1e6:,.{dec}f}M"
    elif a >= 1e3:
        s = f"${a/1e3:,.0f}K"
    else:
        s = f"${a:,.0f}"
    return f"-{s}" if v < 0 else s


def pct(v, dec=2, sign=True):
    if v is None:
        return "—"
    return f"{v:+.{dec}f}%" if sign else f"{v:.{dec}f}%"


def tone(v):
    if v is None:
        return ""
    return "pos" if v > 0 else ("neg" if v < 0 else "muted")


def num(v, dec=0):
    if v is None:
        return "—"
    return f"{v:,.{dec}f}"


def dfmt(v, f="%b %d, %Y"):
    if not v:
        return "—"
    return v.strftime(f)


def ago(v):
    if not v:
        return "—"
    now = datetime.utcnow()
    if isinstance(v, date) and not isinstance(v, datetime):
        v = datetime(v.year, v.month, v.day)
    d = now - v
    s = d.total_seconds()
    if s < 0:
        return "just now"
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s//60)}m ago"
    if s < 86400:
        return f"{int(s//3600)}h ago"
    if d.days < 45:
        return f"{d.days}d ago"
    return v.strftime("%b %d, %Y")


def register(app):
    for f in (money, money_short, pct, tone, num, dfmt, ago):
        app.jinja_env.filters[f.__name__] = f

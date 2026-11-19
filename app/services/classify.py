"""Rule-based document classifier: keyword rules for the kind, name matching for the investment, property, deal or entity."""
import re

from ..models import Deal, Entity, Investment, Property

RULES = [
    ("Capital call", ["capital call", "drawdown", "call notice", "contribution notice"], "pevc"),
    ("Distribution notice", ["distribution", "dist notice", "proceeds"], "family-office"),
    ("Quarterly statement", ["quarterly statement", "quarterly report", "investor letter", "net asset value"], "pevc"),
    ("Capital account", ["capital account", "cap acct", "partner statement", "rollforward"], "pevc"),
    ("Deal materials", ["teaser", "cim", "information memorandum", "pitch deck", "term sheet"], "deals"),
    ("K-1", ["k-1", "k1", "schedule k"], "family-office"),
    ("Bank statement", ["bank statement", "account statement", "checking", "money market"], "family-office"),
    ("Brokerage statement", ["brokerage", "trade confirm", "1099-b", "custody statement"], "stocks"),
    ("Invoice", ["invoice", "bill", "amount due", "remit"], "family-office"),
    ("Property report", ["rent roll", "operating statement", "property report", "t-12", "budget variance"], "real-estate"),
    ("Insurance", ["policy", "insurance", "certificate of insurance", "renewal"], "family-office"),
    ("Contract", ["agreement", "contract", "side letter", "lpa", "subscription"], "documents"),
    ("Tax", ["form 1065", "1041", "estimated tax", "irs", "franchise tax"], "family-office"),
    ("Legal", ["operating agreement", "trust deed", "resolution", "amendment"], "family-office"),
]
STOP = {"the", "fund", "partners", "capital", "llc", "lp", "inc", "holdings", "group", "series", "and", "company", "co", "trust", "family", "alladin", "services", "fund", "group", "statement", "notice", "report"}


def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in STOP}


def classify(filename, text=""):
    hay = f"{filename} {text}".lower().replace("_", " ").replace("-", " ").replace(".", " ")
    hay_k1 = f"{filename} {text}".lower()
    best = ("Other", 0, "documents")
    for kind, kws, app in RULES:
        hits = sum(1 for k in kws if re.search(r"\b" + re.escape(k) + r"\b", hay) or re.search(r"\b" + re.escape(k) + r"\b", hay_k1))
        if hits > best[1]:
            best = (kind, hits, app)
    kind, hits, app = best
    words = _tokens(hay)
    match = None
    mscore = 0
    for model, attr in ((Investment, "investment"), (Property, "property"), (Deal, "deal"), (Entity, "entity")):
        for o in model.query.all():
            t = _tokens(o.name)
            if not t:
                continue
            s = len(t & words) / len(t) + 0.01 * len(t & words)
            if s > mscore and s >= 0.5:
                match, mscore = (attr, o), s
    if match and match[0] == "property" and kind == "Other":
        kind, app = "Property report", "real-estate"
    if match and match[0] == "deal":
        app = "deals"
    period = None
    m = re.search(r"(20\d\d)[ _-]?q([1-4])", hay) or re.search(r"q([1-4])[ _-]?(20\d\d)", hay)
    if m:
        a, b_ = m.groups()
        period = f"{a}Q{b_}" if len(a) == 4 else f"{b_}Q{a}"
    amt = None
    m = re.search(r"\$\s?([\d,]{4,}(?:\.\d\d)?)", text or "")
    if m:
        amt = float(m.group(1).replace(",", ""))
    conf = min(0.99, 0.35 + 0.2 * min(hits, 2) + 0.4 * min(mscore, 1.0))
    return dict(kind=kind, app=app, target=match, period=period, amount=amt, confidence=round(conf, 2))

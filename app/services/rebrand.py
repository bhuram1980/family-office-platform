"""Rename the family across text stored in the database (display names, notes, emails).

Usernames, ids and password hashes are never touched. Order matters: specific phrases first.
"""
import sqlalchemy as sa

from ..extensions import db

PAIRS = [
    ("Tirumala Bhuram", "Tirumala"),
    ("T. Bhuram", "Tirumala"),
    ("bhuram-fo", "alladin-fo"),
    ("Bhuram", "Alladin"),
    ("BHURAM", "ALLADIN"),
    ("bhuram", "alladin"),
]
SKIP_COLUMNS = {("users", "username"), ("users", "password_hash"), ("login_events", "username"), ("alembic_version", "version_num")}


def rebrand(pairs=PAIRS):
    """Returns {table.column: rows changed}."""
    changed = {}
    for table in db.metadata.sorted_tables:
        for col in table.columns:
            if not isinstance(col.type, (sa.String, sa.Text)) or (table.name, col.name) in SKIP_COLUMNS:
                continue
            expr = col
            for old, new in pairs:
                expr = sa.func.replace(expr, old, new)
            first = pairs[-1][0]
            cond = sa.or_(*[col.contains(o) for o, _ in pairs])
            n = db.session.execute(table.update().where(cond).values({col.name: expr})).rowcount
            if n:
                changed[f"{table.name}.{col.name}"] = n
    db.session.commit()
    return changed

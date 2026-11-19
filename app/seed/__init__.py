"""Synthetic seed data. Every name and figure here is invented."""
import importlib
import importlib.util
import random

from ..extensions import db

MODULES = ["core", "stocks", "family_office", "deals", "pevc", "documents",
           "philanthropy", "tasks", "real_estate", "ir_portal"]


def run(reset=True, seed=7):
    if reset:
        db.drop_all()
        db.create_all()
    ctx = {"rnd": random.Random(seed)}
    for name in MODULES:
        if importlib.util.find_spec(f"{__name__}.{name}") is None:
            continue
        mod = importlib.import_module(f".{name}", __name__)
        mod.seed(ctx)
        db.session.commit()
    return ctx

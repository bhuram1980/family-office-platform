"""Real estate shares the FO property tables; here we only run the issue rules once so the queue is populated."""
from ..services.re_rules import run_checks


def seed(ctx):
    run_checks()

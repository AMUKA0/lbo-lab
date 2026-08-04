"""Modelling a deal that does not make it to the end.

A bare "the structure fails" is a dead end that reads like a defect. The useful
statement is *when* it breaks and how far it got, so a reader can watch the
liquidity drain year by year rather than take the verdict on trust. That is what
a credit committee would actually want: "this breaks in year three" is
information; "failed" is not.

This lives in the engine rather than the API because it is financial reasoning,
not transport — the same rule that keeps every other calculation out of `api/`.
It was in `api/main.py` until covenants arrived and exposed why that was wrong:
the truncation has to know about every per-year schedule the engine accepts, and
a transport layer has no business tracking that.
"""

from __future__ import annotations

from lbo_engine.assumptions import Assumptions
from lbo_engine.engine import run_lbo


def truncate(a: Assumptions, years: int) -> Assumptions:
    """The same deal over a shorter hold.

    EVERY per-year schedule comes with it, not just the operating ones. A
    covenant step-down left at full length makes the engine reject the shortened
    deal for a length mismatch — and callers are usually inside an
    `except ValueError`, where that rejection is indistinguishable from the
    structure failing in year one. It reported "survived 0 years" on a deal that
    serviced four of them.
    """
    shorter = a.model_copy(deep=True)
    shorter.hold_years = years
    shorter.operating.revenue_growth = a.growth_schedule()[:years]
    shorter.operating.ebitda_margin = a.margin_schedule()[:years]
    for name in ("net_leverage_ceiling", "interest_coverage_floor"):
        schedule = a.covenant_schedule(name)
        if schedule is not None:
            setattr(shorter.covenants, name, schedule[:years])
    return shorter


def survivable_years(a: Assumptions) -> int:
    """The longest hold this structure can actually service.

    Cheap to compute — at most `hold_years` engine runs on a deal we already
    know is small — and worth far more than the boolean it replaces.
    """
    for years in range(a.hold_years - 1, 0, -1):
        try:
            run_lbo(truncate(a, years))
            return years
        except ValueError:
            continue
    return 0

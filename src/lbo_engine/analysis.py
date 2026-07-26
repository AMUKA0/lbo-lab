"""Analysis layer: every function here is just the engine called many times
with perturbed inputs. Nothing reaches inside the engine's mechanics.
"""

from __future__ import annotations

import math

import pandas as pd

from lbo_engine.assumptions import Assumptions
from lbo_engine.engine import run_lbo
from lbo_engine.returns import sponsor_irr


def _irr_for(a: Assumptions) -> float:
    """IRR for a variant, or NaN where the structure fails (revolver exhausted)
    or the sponsor is wiped out — a NaN cell in a sensitivity grid is honest,
    a fabricated number is not."""
    try:
        result = run_lbo(a)
        if result.exit_equity <= 0:
            return float("nan")
        return sponsor_irr(result)
    except ValueError:
        return float("nan")


def entry_exit_sensitivity(
    base: Assumptions,
    entry_multiples: list[float],
    exit_multiples: list[float],
) -> pd.DataFrame:
    """IRR grid across entry multiple (rows) × exit multiple (columns).

    Note that changing the entry multiple re-levers the deal: debt is sized in
    turns of EBITDA, so a richer entry price means a bigger equity cheque, not
    more debt — exactly how it works in practice.
    """
    rows = {}
    for em in entry_multiples:
        row = {}
        for xm in exit_multiples:
            variant = base.model_copy(deep=True)
            variant.entry_multiple = em
            variant.exit_multiple = xm
            row[xm] = _irr_for(variant)
        rows[em] = row
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "entry_multiple"
    df.columns.name = "exit_multiple"
    return df


def debt_paydown_table(a: Assumptions) -> pd.DataFrame:
    """Closing balance per tranche (plus revolver and cash) by year, including
    year 0 at close — the data behind the deleveraging chart."""
    r = run_lbo(a)
    su = r.sources_uses
    records = [
        {
            "year": 0,
            "cash": su.cash_to_balance_sheet,
            "revolver": 0.0,
            **su.tranche_amounts,
        }
    ]
    for row in r.years:
        records.append(
            {
                "year": row.year,
                "cash": row.closing_cash,
                "revolver": row.revolver_closing,
                **{name: t.closing for name, t in row.tranches.items()},
            }
        )
    return pd.DataFrame.from_records(records).set_index("year")


def is_valid_irr(value: float) -> bool:
    return not math.isnan(value)


# --------------------------------------------------------------------- tornado

def _shift_growth(a: Assumptions, d: float) -> None:
    a.operating.revenue_growth = [g + d for g in a.growth_schedule()]


def _shift_margin(a: Assumptions, d: float) -> None:
    a.operating.ebitda_margin = [m + d for m in a.margin_schedule()]


def _shift_entry(a: Assumptions, d: float) -> None:
    a.entry_multiple += d


def _shift_exit(a: Assumptions, d: float) -> None:
    a.exit_multiple += d


def _shift_senior_leverage(a: Assumptions, d: float) -> None:
    a.tranches[0].leverage_turns = max(a.tranches[0].leverage_turns + d, 0.25)


def _shift_capex(a: Assumptions, d: float) -> None:
    a.operating.capex_pct_revenue = max(a.operating.capex_pct_revenue + d, 0.0)


def _shift_tax(a: Assumptions, d: float) -> None:
    a.operating.tax_rate = min(max(a.operating.tax_rate + d, 0.0), 0.6)


# (label, mutator, downside delta, upside delta) — swings sized to be
# comparable real-world uncertainties, not equal percentages.
TORNADO_DRIVERS = [
    ("Exit multiple (±1.0×)", _shift_exit, -1.0, 1.0),
    ("Entry multiple (±1.0×)", _shift_entry, 1.0, -1.0),  # paying MORE is the downside
    ("Revenue growth (±200bps)", _shift_growth, -0.02, 0.02),
    ("EBITDA margin (±200bps)", _shift_margin, -0.02, 0.02),
    ("Senior leverage (±0.5×)", _shift_senior_leverage, -0.5, 0.5),
    ("Capex (±100bps of revenue)", _shift_capex, 0.01, -0.01),  # more capex is the downside
    ("Tax rate (±5pts)", _shift_tax, 0.05, -0.05),
]


def tornado(base: Assumptions) -> pd.DataFrame:
    """One-at-a-time sensitivity: IRR at a downside and upside swing of each
    driver, all others held at base. Sorted by total span, widest first —
    the classic tornado ranking of what actually moves the answer."""
    base_irr = _irr_for(base)
    records = []
    for label, mutate, down, up in TORNADO_DRIVERS:
        low_case = base.model_copy(deep=True)
        mutate(low_case, down)
        high_case = base.model_copy(deep=True)
        mutate(high_case, up)
        low_irr, high_irr = _irr_for(low_case), _irr_for(high_case)
        span = abs(high_irr - low_irr) if is_valid_irr(low_irr) and is_valid_irr(high_irr) else float("inf")
        records.append({"driver": label, "low_irr": low_irr, "high_irr": high_irr, "span": span})
    df = pd.DataFrame.from_records(records).sort_values("span", ascending=False).drop(columns="span")
    df["base_irr"] = base_irr
    return df.set_index("driver")


# ------------------------------------------------------------------- scenarios

def apply_recession(
    base: Assumptions,
    *,
    ebitda_shock: float = 0.20,
    shock_years: int = 2,
    exit_haircut: float = 1.5,
) -> Assumptions:
    """The canned downturn: EBITDA margin cut by `ebitda_shock` (relative) in the
    first `shock_years`, exit multiple down `exit_haircut` turns. Answers the
    only stress question that matters: does the capital structure survive?"""
    stressed = base.model_copy(deep=True)
    margins = base.margin_schedule()
    stressed.operating.ebitda_margin = [
        m * (1 - ebitda_shock) if i < shock_years else m for i, m in enumerate(margins)
    ]
    stressed.exit_multiple = max(base.exit_multiple - exit_haircut, 1.0)
    return stressed


def scenario_set(base: Assumptions) -> dict[str, Assumptions]:
    """Base / upside / downside / recession — the standard IC presentation set.
    Swings are deliberately conventional: ±200bps growth, ±100bps margin,
    ±0.5–1.0× exit."""
    upside = base.model_copy(deep=True)
    _shift_growth(upside, 0.02)
    _shift_margin(upside, 0.01)
    upside.exit_multiple += 0.5

    downside = base.model_copy(deep=True)
    _shift_growth(downside, -0.02)
    _shift_margin(downside, -0.01)
    downside.exit_multiple = max(base.exit_multiple - 1.0, 1.0)

    return {
        "Base": base.model_copy(deep=True),
        "Upside": upside,
        "Downside": downside,
        "Recession stress": apply_recession(base),
    }


# ------------------------------------------------------------------- breakeven

def breakeven_exit_multiple(
    base: Assumptions, target_irr: float, *, lo: float = 1.0, hi: float = 40.0
) -> float:
    """The exit multiple at which the deal clears `target_irr` — the model run
    in reverse. Bisection works because IRR is monotonically increasing in the
    exit multiple. Returns NaN if the target is unreachable inside [lo, hi]."""

    def f(multiple: float) -> float:
        variant = base.model_copy(deep=True)
        variant.exit_multiple = multiple
        value = _irr_for(variant)
        # A wiped-out sponsor is as far below target as it gets.
        return (value if is_valid_irr(value) else -1.0) - target_irr

    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0:
        return lo  # already clears the target at the floor
    if f_hi < 0:
        return float("nan")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if abs(hi - lo) < 1e-6:
            return mid
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)

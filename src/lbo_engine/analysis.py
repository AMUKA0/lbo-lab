"""Analysis layer: every function here is just the engine called many times
with perturbed inputs. Nothing reaches inside the engine's mechanics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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


# ----------------------------------------------------------------- credit view

def credit_stats(a: Assumptions) -> pd.DataFrame:
    """The lender's dashboard, by year: net leverage, interest coverage,
    (EBITDA − capex) coverage, and FCF conversion. These are the covenant-style
    ratios a credit committee watches; a sponsor who can't speak to them
    doesn't get financed."""
    r = run_lbo(a)
    records = []
    for row in r.years:
        net_debt = row.total_debt_closing - row.closing_cash
        records.append({
            "year": row.year,
            "net_leverage": net_debt / row.ebitda if row.ebitda > 0 else float("nan"),
            "interest_coverage": (
                row.ebitda / row.cash_interest_total if row.cash_interest_total > 0 else float("inf")
            ),
            "ebitda_less_capex_coverage": (
                (row.ebitda - row.capex) / row.cash_interest_total
                if row.cash_interest_total > 0 else float("inf")
            ),
            "fcf_conversion": (
                row.cash_available_for_debt_service / row.ebitda if row.ebitda > 0 else float("nan")
            ),
        })
    return pd.DataFrame.from_records(records).set_index("year")


# ------------------------------------------------------------------ exit timing

def exit_year_profile(a: Assumptions) -> pd.DataFrame:
    """IRR and MOIC if the sponsor exited at the end of each year instead of
    the assumed hold, exit multiple unchanged. Shows the shape of the deal in
    time: deleveraging compounds MOIC while the annualisation drags IRR — the
    classic hold-longer-vs-flip tension."""
    growth = a.growth_schedule()
    margin = a.margin_schedule()
    records = []
    for k in range(2, a.hold_years + 1):
        variant = a.model_copy(deep=True)
        variant.hold_years = k
        variant.operating.revenue_growth = growth[:k]
        variant.operating.ebitda_margin = margin[:k]
        try:
            res = run_lbo(variant)
            moic = res.moic if res.exit_equity > 0 else float("nan")
        except ValueError:
            records.append({"exit_year": k, "irr": float("nan"), "moic": float("nan")})
            continue
        records.append({"exit_year": k, "irr": _irr_for(variant), "moic": moic})
    return pd.DataFrame.from_records(records).set_index("exit_year")


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


# --------------------------------------------------------------- lifecycle
#
# A deal is usually shown as a table of years, which is the right format for
# checking arithmetic and the wrong one for understanding what happened. The
# lifecycle re-reads the same schedule as a sequence of *events* — the moments
# where something was decided or something gave way — so the story of the hold
# is legible without reading twenty rows of numbers.
#
# Nothing here computes: every event is derived from a run the engine has
# already produced. It is a reading of the model, not a second model.

@dataclass(frozen=True)
class LifecycleEvent:
    year: int          # 0 = close, hold_years = exit
    kind: str          # machine-readable; the client keys styling off this
    title: str
    detail: str
    tone: str          # "neutral" | "good" | "watch" | "bad"


# Coverage below this is where a credit committee starts paying attention, and
# where most maintenance covenants of the modern era were actually set.
_COVERAGE_WATCH = 2.0
_LEVERAGE_WATCH = 6.0


def lifecycle(result) -> list[LifecycleEvent]:
    """The hold as a sequence of decisions and pressure points."""
    a = result.assumptions
    su = result.sources_uses
    events: list[LifecycleEvent] = [
        LifecycleEvent(
            year=0,
            kind="entry",
            title="Investment",
            detail=(
                f"{_m(su.entry_ev)} enterprise value at {a.entry_multiple:.1f}× "
                f"{_m(a.entry_ebitda)} of EBITDA. "
                f"{_m(su.total_debt)} of debt across {len(a.tranches)} "
                f"{'tranche' if len(a.tranches) == 1 else 'tranches'} "
                f"({a.total_leverage_turns:.1f}× leverage), "
                f"{_m(su.sponsor_equity)} of sponsor equity."
            ),
            tone="neutral",
        )
    ]

    prev_revolver = 0.0
    for y in result.years:
        coverage = y.ebitda / y.cash_interest_total if y.cash_interest_total > 0 else None
        leverage = (y.total_debt_closing - y.closing_cash) / y.ebitda if y.ebitda else None

        if y.pik_elections:
            names = ", ".join(y.pik_elections)
            events.append(LifecycleEvent(
                year=y.year, kind="pik_toggle",
                title=f"PIK toggle elected — {names}",
                detail=(
                    "Operating cash flow could not cover the full cash coupon, so the "
                    "issuer exercised its option to accrue interest to principal "
                    "instead of defaulting. This buys the year at the cost of a higher "
                    "balance and a stepped-up rate compounding into every year after "
                    "it — relief, not a cure."
                ),
                tone="watch",
            ))

        if y.recap_raised > 0:
            events.append(LifecycleEvent(
                year=y.year, kind="recap",
                title=f"Dividend recapitalisation — {_m(y.recap_dividend)} to the sponsor",
                detail=(
                    f"{_m(y.recap_raised)} of incremental debt raised, "
                    f"{_m(y.recap_fee)} of financing fees, "
                    f"{_m(y.recap_dividend)} paid out. Creates no enterprise value: it "
                    "converts future equity into present cash and pays interest for the "
                    "privilege, which lifts IRR while leaving MOIC flat to slightly down."
                ),
                tone="good",
            ))
        elif y.recap_target > 0:
            events.append(LifecycleEvent(
                year=y.year, kind="recap_unfunded",
                title="Recap not fundable",
                detail=(
                    "The target leverage sits below where the company already is, so a "
                    "recap would mean repaying debt rather than raising it. Nothing "
                    "was paid out."
                ),
                tone="watch",
            ))

        if y.revolver_closing > 0 and prev_revolver == 0:
            drawn = y.revolver_closing / a.revolver.commitment if a.revolver.commitment else 0
            events.append(LifecycleEvent(
                year=y.year, kind="revolver",
                title=f"Revolver drawn — {_m(y.revolver_closing)}",
                detail=(
                    f"{drawn:.0%} of the commitment. The revolver is the shock absorber: "
                    "a draw means the year's operating cash did not cover its contractual "
                    "obligations, and the facility is finite."
                ),
                tone="watch",
            ))
        prev_revolver = y.revolver_closing

        if coverage is not None and coverage < _COVERAGE_WATCH:
            events.append(LifecycleEvent(
                year=y.year, kind="coverage",
                title=f"Interest coverage {coverage:.2f}×",
                detail=(
                    f"EBITDA covers cash interest {coverage:.2f} times, below the {_COVERAGE_WATCH:.1f}× "
                    "level most maintenance covenants of the modern era were set at. "
                    "Not a default in this model, which tests liquidity rather than "
                    "covenants — but the point where a lender starts asking questions."
                ),
                tone="bad" if coverage < 1.0 else "watch",
            ))

        if leverage is not None and leverage > _LEVERAGE_WATCH:
            events.append(LifecycleEvent(
                year=y.year, kind="leverage",
                title=f"Net leverage {leverage:.2f}×",
                detail=(
                    f"Above the {_LEVERAGE_WATCH:.1f}× the guardrails flag as outside the "
                    "market band for a sustainable structure."
                ),
                tone="watch",
            ))

    last = result.years[-1]
    wiped = result.exit_equity <= 0
    events.append(LifecycleEvent(
        year=a.hold_years,
        kind="exit",
        title="Exit" if not wiped else "Exit — sponsor wiped out",
        detail=(
            f"{a.exit_multiple:.1f}× on {_m(result.exit_ebitda)} of terminal EBITDA = "
            f"{_m(result.exit_ev)} enterprise value, less {_m(result.exit_net_debt)} of net "
            f"debt and {_m(result.exit_fees)} of sale costs. "
            + (
                "Net debt exceeds enterprise value, so the equity is worth nothing and "
                "is floored at zero — limited liability."
                if wiped
                else f"{_m(result.exit_equity)} of equity proceeds."
            )
        ),
        tone="bad" if wiped else "good",
    ))
    return events


def _m(value: float) -> str:
    """Money, at the scale the number deserves."""
    if abs(value) >= 1000:
        return f"${value / 1000:,.1f}bn"
    return f"${value:,.0f}m"

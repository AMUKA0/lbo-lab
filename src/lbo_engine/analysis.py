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

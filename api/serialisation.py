"""Engine dataclasses → JSON-safe response models.

Two jobs, both boring on purpose:

1. **Total fidelity.** Every field the engine computes is carried through —
   per-tranche opening/interest/PIK/amortisation/sweep/closing, the NOL roll,
   the iteration count of the interest solve. The web client is a *view* of the
   model, not a summary of it. If a number exists in `YearRow` it exists here.

2. **Valid JSON.** The engine legitimately produces NaN (a structure that fails,
   a wiped-out sponsor) and inf (interest coverage with no interest). Neither is
   representable in JSON, and `JSON.parse` rejects both. They become `null`, and
   the client renders `null` as "n/a" rather than inventing a number.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from lbo_engine.assumptions import Assumptions
from lbo_engine.calibration import Flag
from lbo_engine.engine import LBOResult, YearRow
from lbo_engine.returns import ReturnsBridge, sponsor_irr
from lbo_engine.sources_uses import SourcesAndUses


def jsonable(value: Any) -> Any:
    """Recursively replace NaN/±inf with None so the payload is strict JSON."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


# --------------------------------------------------------------- sub-models

class TrancheYearOut(BaseModel):
    name: str
    opening: float
    cash_interest: float
    pik_accrual: float
    mandatory_repayment: float
    sweep_repayment: float
    closing: float
    pik_elected: bool


class YearOut(BaseModel):
    year: int
    revenue: float
    ebitda: float
    ebitda_margin: float
    da: float
    ebit: float
    capex: float
    delta_nwc: float
    fee_amortisation: float
    cash_interest_total: float
    pik_accrual_total: float
    revolver_undrawn_fee: float
    ebt: float
    nol_opening: float
    nol_used: float
    nol_closing: float
    taxes: float
    net_income: float
    cash_available_for_debt_service: float
    revolver_opening: float
    revolver_draw: float
    revolver_repayment: float
    revolver_closing: float
    opening_cash: float
    closing_cash: float
    total_debt_closing: float
    net_debt_closing: float
    # Tranches on which the PIK toggle was elected this year.
    pik_elections: list[str]
    # Follow-on sponsor capital, and any debt extinguished alongside it.
    equity_injected: float
    debt_retired: float
    # Dividend recap, if one fell in this year. `raised` is gross incremental
    # debt; `dividend` is what reached the sponsor after the financing fee.
    recap_target: float
    recap_raised: float
    recap_fee: float
    recap_dividend: float
    interest_iterations: int
    tranches: list[TrancheYearOut]


class SourcesUsesOut(BaseModel):
    entry_ev: float
    transaction_fees: float
    financing_fees: float
    cash_to_balance_sheet: float
    total_uses: float
    tranche_amounts: dict[str, float]
    total_debt: float
    sponsor_equity: float
    total_sources: float


class BridgeOut(BaseModel):
    ebitda_growth: float
    multiple_expansion: float
    deleveraging: float
    recapitalisation: float
    follow_on_equity: float
    fee_drag: float
    entry_equity: float
    exit_equity: float
    dividends: float
    total_invested: float
    total_proceeds: float
    total_value_created: float
    # The identity the test suite asserts, surfaced so the UI can prove it on
    # screen rather than asking to be trusted. Note it reconciles against TOTAL
    # proceeds — exit equity plus recap dividends — not against exit equity
    # alone, which would be short by every dollar taken out early.
    equity_gain: float
    reconciliation_error: float


class FlagOut(BaseModel):
    field: str
    level: str
    message: str
    source: str


class LifecycleEventOut(BaseModel):
    """One moment in the hold. Derived from the run, never computed anew."""

    year: int
    kind: str
    title: str
    detail: str
    tone: str


class CreditYearOut(BaseModel):
    year: int
    net_leverage: float | None
    interest_coverage: float | None
    # Cash interest plus PIK. Diverges sharply from the cash figure wherever a
    # PIK strip is compounding, which is exactly where it matters.
    total_interest_coverage: float | None
    ebitda_less_capex_coverage: float | None
    fcf_conversion: float | None


class RunOut(BaseModel):
    """Everything a single deal run produces."""

    sources_uses: SourcesUsesOut
    years: list[YearOut]
    tranche_names: list[str]
    exit_ebitda: float
    exit_ev: float
    exit_net_debt: float
    exit_fees: float
    exit_equity: float
    entry_equity: float
    entry_net_debt: float
    entry_net_leverage: float | None
    exit_net_leverage: float | None
    moic: float | None
    irr: float | None
    equity_cash_flows: list[float]
    bridge: BridgeOut
    lifecycle: list[LifecycleEventOut]
    credit: list[CreditYearOut]
    flags: list[FlagOut]
    # True when the sponsor is wiped out; IRR/MOIC are null and the UI says so.
    wiped_out: bool


# ---------------------------------------------------------------- converters

def su_out(su: SourcesAndUses) -> SourcesUsesOut:
    return SourcesUsesOut(
        entry_ev=su.entry_ev,
        transaction_fees=su.transaction_fees,
        financing_fees=su.financing_fees,
        cash_to_balance_sheet=su.cash_to_balance_sheet,
        total_uses=su.total_uses,
        tranche_amounts=dict(su.tranche_amounts),
        total_debt=su.total_debt,
        sponsor_equity=su.sponsor_equity,
        total_sources=su.total_sources,
    )


def year_out(y: YearRow) -> YearOut:
    return YearOut(
        year=y.year,
        revenue=y.revenue,
        ebitda=y.ebitda,
        ebitda_margin=y.ebitda / y.revenue if y.revenue else 0.0,
        da=y.da,
        ebit=y.ebit,
        capex=y.capex,
        delta_nwc=y.delta_nwc,
        fee_amortisation=y.fee_amortisation,
        cash_interest_total=y.cash_interest_total,
        pik_accrual_total=y.pik_accrual_total,
        revolver_undrawn_fee=y.revolver_undrawn_fee,
        ebt=y.ebt,
        nol_opening=y.nol_opening,
        nol_used=y.nol_used,
        nol_closing=y.nol_closing,
        taxes=y.taxes,
        net_income=y.net_income,
        cash_available_for_debt_service=y.cash_available_for_debt_service,
        revolver_opening=y.revolver_opening,
        revolver_draw=y.revolver_draw,
        revolver_repayment=y.revolver_repayment,
        revolver_closing=y.revolver_closing,
        opening_cash=y.opening_cash,
        closing_cash=y.closing_cash,
        total_debt_closing=y.total_debt_closing,
        net_debt_closing=y.total_debt_closing - y.closing_cash,
        pik_elections=list(y.pik_elections),
        equity_injected=y.equity_injected,
        debt_retired=y.debt_retired,
        recap_target=y.recap_target,
        recap_raised=y.recap_raised,
        recap_fee=y.recap_fee,
        recap_dividend=y.recap_dividend,
        interest_iterations=y.interest_iterations,
        tranches=[
            TrancheYearOut(
                name=name,
                opening=t.opening,
                cash_interest=t.cash_interest,
                pik_accrual=t.pik_accrual,
                mandatory_repayment=t.mandatory_repayment,
                sweep_repayment=t.sweep_repayment,
                closing=t.closing,
                pik_elected=t.pik_elected,
            )
            for name, t in y.tranches.items()
        ],
    )


def bridge_out(b: ReturnsBridge) -> BridgeOut:
    gain = b.total_proceeds - b.total_invested
    return BridgeOut(
        ebitda_growth=b.ebitda_growth,
        multiple_expansion=b.multiple_expansion,
        deleveraging=b.deleveraging,
        recapitalisation=b.recapitalisation,
        follow_on_equity=b.follow_on_equity,
        fee_drag=b.fee_drag,
        entry_equity=b.entry_equity,
        exit_equity=b.exit_equity,
        dividends=b.dividends,
        total_invested=b.total_invested,
        total_proceeds=b.total_proceeds,
        total_value_created=b.total_value_created,
        equity_gain=gain,
        reconciliation_error=b.total_value_created - gain,
    )


def flag_out(f: Flag) -> FlagOut:
    return FlagOut(field=f.field, level=f.level, message=f.message, source=f.source)


def run_out(r: LBOResult, flags: list[Flag], credit_records: list[dict]) -> RunOut:
    a: Assumptions = r.assumptions
    wiped = r.exit_equity <= 0

    try:
        irr_value = None if wiped else sponsor_irr(r)
    except ValueError:
        irr_value = None

    from lbo_engine.analysis import lifecycle
    from lbo_engine.returns import returns_bridge

    last = r.years[-1]
    return RunOut(
        sources_uses=su_out(r.sources_uses),
        years=[year_out(y) for y in r.years],
        tranche_names=[t.name for t in a.tranches],
        exit_ebitda=r.exit_ebitda,
        exit_ev=r.exit_ev,
        exit_net_debt=r.exit_net_debt,
        exit_fees=r.exit_fees,
        exit_equity=r.exit_equity,
        entry_equity=r.entry_equity,
        entry_net_debt=r.entry_net_debt,
        entry_net_leverage=r.entry_net_debt / a.entry_ebitda if a.entry_ebitda else None,
        exit_net_leverage=r.exit_net_debt / last.ebitda if last.ebitda else None,
        moic=None if wiped else r.moic,
        irr=irr_value,
        equity_cash_flows=list(r.equity_cash_flows),
        bridge=bridge_out(returns_bridge(r)),
        lifecycle=[
            LifecycleEventOut(year=e.year, kind=e.kind, title=e.title, detail=e.detail, tone=e.tone)
            for e in lifecycle(r)
        ],
        credit=[CreditYearOut(**jsonable(rec)) for rec in credit_records],
        flags=[flag_out(f) for f in flags],
        wiped_out=wiped,
    )

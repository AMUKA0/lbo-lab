"""Starting points for the client.

The default deal is deliberately *unremarkable*: a mid-market services business
at 11× with 5.5 turns of leverage, held five years, exited flat-to-slightly-up.
Every number sits inside the calibration bands, so a first-time visitor sees a
clean run and has to work to break it — which is the right way round.
"""

from __future__ import annotations

from lbo_engine import (
    Assumptions,
    DebtTranche,
    OperatingAssumptions,
    RevolverAssumptions,
)


def default_deal() -> Assumptions:
    return Assumptions(
        entry_ebitda=100.0,
        entry_multiple=11.0,
        operating=OperatingAssumptions(
            entry_revenue=520.0,
            revenue_growth=0.05,
            ebitda_margin=0.198,
            da_pct_revenue=0.035,
            capex_pct_revenue=0.040,
            nwc_pct_revenue=0.10,
            tax_rate=0.25,
        ),
        tranches=[
            DebtTranche(
                name="Senior term loan",
                leverage_turns=4.0,
                cash_rate=0.055,
                mandatory_amort_pct=0.05,
                sweepable=True,
            ),
            DebtTranche(
                name="Mezzanine",
                leverage_turns=1.5,
                cash_rate=0.08,
                pik_rate=0.03,
                sweepable=False,
            ),
        ],
        revolver=RevolverAssumptions(commitment=50.0, cash_rate=0.06, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.015,
        financing_fee_pct_debt=0.025,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.01,
        nol_limit_pct=0.8,
        interest_on_average_balance=True,
        minimum_cash=10.0,
        cash_sweep_pct=0.75,
        hold_years=5,
        exit_multiple=11.5,
    )


def _preset(name: str, blurb: str, mutate) -> dict:
    deal = default_deal()
    mutate(deal)
    return {"name": name, "blurb": blurb, "assumptions": deal.model_dump()}


def _conservative(d: Assumptions) -> None:
    d.tranches[0].leverage_turns = 3.5
    d.tranches[1].leverage_turns = 0.5
    d.exit_multiple = d.entry_multiple
    d.cash_sweep_pct = 1.0


def _aggressive(d: Assumptions) -> None:
    d.entry_multiple = 13.0
    d.tranches[0].leverage_turns = 5.0
    d.tranches[1].leverage_turns = 2.0
    d.exit_multiple = 14.0
    d.operating.revenue_growth = 0.09


def _2007(d: Assumptions) -> None:
    # The vintage the guardrails exist to warn you about.
    d.entry_multiple = 13.5
    d.tranches[0].leverage_turns = 5.5
    d.tranches[1].leverage_turns = 2.5
    d.tranches[0].cash_rate = 0.075
    d.exit_multiple = 9.5
    d.operating.revenue_growth = [0.08, -0.06, -0.04, 0.03, 0.05]
    d.revolver.commitment = 120.0
    d.hold_years = 5


PRESETS = [
    {
        "name": "Base case",
        "blurb": "Mid-market services business, 11× entry, 5.5 turns, five-year hold. Everything inside the market bands.",
        "assumptions": default_deal().model_dump(),
    },
    _preset(
        "Conservative structure",
        "Four turns of leverage, full cash sweep, exit underwritten flat to entry. The discipline case.",
        _conservative,
    ),
    _preset(
        "Aggressive underwrite",
        "13× entry, seven turns, multiple expansion assumed. Watch what the guardrails say.",
        _aggressive,
    ),
    _preset(
        "2007 vintage",
        "Peak-of-cycle pricing and leverage into a downturn, exiting into a compressed market.",
        _2007,
    ),
]

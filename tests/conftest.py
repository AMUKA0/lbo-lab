"""Shared fixtures: two reference deals.

`simple_deal` is fully hand-computable (flat operations, one tranche, no taxes
or fees) — the golden case whose every balance is asserted to 6 decimals in
test_engine.py, derived by solving the interest circularity algebraically.

`rich_deal` exercises every feature at once: growth, margin path, taxes, fees,
two tranches with PIK, mandatory amortisation, a revolver and a partial sweep.
Used for invariant tests (identities that must hold regardless of inputs).
"""

import pytest

from lbo_engine import Assumptions, DebtTranche, OperatingAssumptions, RevolverAssumptions


@pytest.fixture
def simple_deal() -> Assumptions:
    return Assumptions(
        entry_ebitda=100.0,
        entry_multiple=10.0,
        operating=OperatingAssumptions(
            entry_revenue=500.0,
            revenue_growth=0.0,
            ebitda_margin=0.20,
            da_pct_revenue=0.0,
            capex_pct_revenue=0.0,
            nwc_pct_revenue=0.0,
            tax_rate=0.0,
        ),
        tranches=[
            DebtTranche(name="senior", leverage_turns=4.0, cash_rate=0.05),
        ],
        hold_years=3,
        exit_multiple=10.0,
    )


@pytest.fixture
def rich_deal() -> Assumptions:
    return Assumptions(
        entry_ebitda=100.0,
        entry_multiple=11.0,
        operating=OperatingAssumptions(
            entry_revenue=520.0,
            revenue_growth=[0.06, 0.05, 0.05, 0.04, 0.04],
            ebitda_margin=[0.192, 0.195, 0.198, 0.200, 0.202],
            da_pct_revenue=0.035,
            capex_pct_revenue=0.040,
            nwc_pct_revenue=0.10,
            tax_rate=0.25,
        ),
        tranches=[
            DebtTranche(
                name="senior_tl",
                leverage_turns=4.0,
                cash_rate=0.055,
                mandatory_amort_pct=0.05,
                sweepable=True,
            ),
            DebtTranche(
                name="mezzanine",
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
        minimum_cash=10.0,
        cash_sweep_pct=0.75,
        hold_years=5,
        exit_multiple=11.5,
    )

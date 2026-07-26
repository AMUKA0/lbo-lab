# LBO Engine

A pure, deterministic, deal-level leveraged-buyout model in Python. Assumptions in, fully populated model out — no I/O, no state. This is Phase 1 of the LBO Simulator project: the maths that everything else (calibration layer, case-study library, web UI) sits on top of.

## Methodology — and where it matches industry practice

The engine follows standard sponsor-model conventions throughout:

| Step | Convention used |
|---|---|
| **Entry** | Cash-free / debt-free purchase. Entry EV = entry EBITDA × entry multiple. Existing debt refinanced at close; minimum operating cash funded in Uses. |
| **Sources & Uses** | Debt sized in turns of EBITDA per tranche; **sponsor equity is the plug** (Uses − total debt). Transaction fees on EV; financing fees (OID/arrangement) on funded debt. |
| **Financing fees** | Capitalised at close and amortised straight-line over the hold; the amortisation is non-cash and tax-deductible. |
| **Interest** | Charged on the **average of opening and closing balances**. Since closing balances depend on the cash sweep, which depends on interest, this is circular — resolved by an **iterative solve within each year** (seed with interest on opening balances; recompute until the total charge converges below 1e-10). This mirrors Excel's iterative-calculation mode. |
| **PIK interest** | Accrues on the opening balance and accretes to principal; non-cash and tax-deductible. |
| **Taxes** | On EBT (after all deductible interest and fee amortisation), floored at zero in loss years. |
| **Cash flow** | Net income + D&A + fee amortisation + PIK − capex − ΔNWC = cash available for debt service. ΔNWC = NWC % of revenue × change in revenue. |
| **Debt waterfall** | 1) Mandatory amortisation (% of **original** principal — term-loan convention), 2) revolver repayment, 3) optional prepayment: the sweep % of remaining excess cash, applied **senior-first** to sweepable tranches. Shortfalls draw the revolver; if the revolver is exhausted the model fails loudly rather than printing a broken structure. |
| **Exit** | Exit EV = exit multiple × terminal EBITDA; exit equity = EV − net debt (floored at zero — limited liability). |
| **Returns** | MOIC = exit equity / equity cheque. IRR by bisection on the sponsor's cash-flow vector. |
| **Attribution** | The value-creation bridge — (ΔEBITDA × entry multiple) + (Δmultiple × exit EBITDA) + net-debt paydown − fees — **sums exactly to the equity gain**; the test suite asserts the identity. The ΔEBITDA×Δmultiple cross term sits in the multiple line (the most common convention). |

## Documented simplifications (v1)

Stated openly, because pretending they don't exist is how models lie:

- **No NOL carryforwards** — loss years pay zero tax but generate no shield for later years (understates returns for deals with early losses).
- **No dividend recaps or interim distributions** — the sponsor's flows are the cheque at close and proceeds at exit.
- **Annual periodicity** — real credit agreements amortise quarterly; annual is the standard teaching/screening convention.
- **Straight-line fee amortisation over the hold** rather than the debt's contractual life; no write-off of unamortised fees on early repayment.
- **No management rollover, option pool, or transaction bonuses** in the equity split.
- **Fixed rates** — no floating-rate curves (SOFR + spread) or hedging.
- **The exit-equity floor at zero** breaks the bridge identity in wipeout scenarios (the bridge is only asserted for solvent exits).

Each of these is a candidate for a later phase; none silently distorts a normal base case.

## Layout

```
src/lbo_engine/
  assumptions.py    # Pydantic input contracts (validated, typed, schedule expansion)
  sources_uses.py   # Entry: S&U with equity as the plug
  engine.py         # The year loop: operating build, iterative interest solve, waterfall
  returns.py        # IRR (bisection), MOIC, value-creation bridge
tests/
  conftest.py       # simple_deal (hand-computable golden case) + rich_deal (all features)
  test_engine.py    # Golden-case assertions to 1e-6 + invariants that must hold for any deal
  test_returns.py   # IRR solver against known closed-form answers
```

## Quick start

```bash
pip install -e ".[dev]"
pytest
```

```python
from lbo_engine import Assumptions, DebtTranche, OperatingAssumptions, run_lbo
from lbo_engine.returns import returns_bridge, sponsor_irr

deal = Assumptions(
    entry_ebitda=100, entry_multiple=10,
    operating=OperatingAssumptions(
        entry_revenue=500, revenue_growth=0.05, ebitda_margin=0.21,
        da_pct_revenue=0.035, capex_pct_revenue=0.04, nwc_pct_revenue=0.10,
        tax_rate=0.25,
    ),
    tranches=[
        DebtTranche(name="senior", leverage_turns=4.0, cash_rate=0.055, mandatory_amort_pct=0.05),
        DebtTranche(name="mezz", leverage_turns=1.0, cash_rate=0.08, pik_rate=0.03, sweepable=False),
    ],
    transaction_fee_pct_ev=0.015, financing_fee_pct_debt=0.025,
    hold_years=5, exit_multiple=10.5,
)

result = run_lbo(deal)
print(f"IRR {sponsor_irr(result):.1%}, MOIC {result.moic:.2f}x")
print(result.to_dataframe())
print(returns_bridge(result))
```

## Verification

The golden case in `tests/test_engine.py` is solved **by hand**: with flat EBITDA and one bullet tranche, the within-year circularity has the closed form `I = r(opening − E/2)/(1 − r/2)`, and every interest charge and closing balance in the test is derived from it independently of the engine. The invariant tests then assert identities that must hold for *any* input: sources = uses, the debt roll-forward, the cash floor, and the bridge summing exactly to the equity gain.

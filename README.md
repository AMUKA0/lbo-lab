# LBO Engine

A pure, deterministic, deal-level leveraged-buyout model in Python. Assumptions in, fully populated model out — no I/O, no state. This is Phase 1 of the LBO Simulator project: the maths that everything else (calibration layer, case-study library, web UI) sits on top of.

## Methodology — and where it matches industry practice

The engine follows standard sponsor-model conventions throughout:

| Step | Convention used |
|---|---|
| **Entry** | Cash-free / debt-free purchase. Entry EV = entry EBITDA × entry multiple. Existing debt refinanced at close; minimum operating cash funded in Uses. |
| **Sources & Uses** | Debt sized in turns of EBITDA per tranche; **sponsor equity is the plug** (Uses − total debt). Transaction fees on EV; financing fees (OID/arrangement) on funded debt. |
| **Financing fees** | Capitalised at close and amortised straight-line over the **facility tenor** (ASC 835-30 debt-issuance-cost treatment), not the hold — so on a 5-year hold of a 7-year facility, part of the fee is never expensed pre-exit. Non-cash and tax-deductible. |
| **Interest** | Charged on the **average of opening and closing balances** — the advanced-model convention, since opening-only overstates interest and closing-only understates it. That makes the model circular (interest → cash → sweep → balances → interest), resolved by an **iterative solve within each year** to a 1e-10 tolerance, mirroring Excel's iterative-calculation mode. A **circularity-breaker toggle** switches to opening-balance-only (acyclic, approximate) — the same escape hatch bank models ship. |
| **PIK interest** | Accrues on the opening balance and accretes to principal; non-cash and tax-deductible. |
| **Taxes** | On EBT (after all deductible interest and fee amortisation). Losses carry forward as **NOLs and shelter up to 80% of later pre-tax income** (post-TCJA §172(a)); the limitation is configurable. |
| **Exit costs** | Sale-process fees (banker, legal) as a % of exit EV, deducted from proceeds — the exit side of the fee drag that many teaching models omit. |
| **Cash flow** | Net income + D&A + fee amortisation + PIK − capex − ΔNWC = cash available for debt service. ΔNWC = NWC % of revenue × change in revenue. |
| **Debt waterfall** | 1) Mandatory amortisation (% of **original** principal — term-loan convention), 2) revolver repayment, 3) optional prepayment: the sweep % of remaining excess cash, applied **senior-first** to sweepable tranches. Shortfalls draw the revolver; if the revolver is exhausted the model fails loudly rather than printing a broken structure. |
| **Exit** | Exit EV = exit multiple × terminal EBITDA; exit equity = EV − net debt (floored at zero — limited liability). |
| **Returns** | MOIC = exit equity / equity cheque. IRR by bisection on the sponsor's cash-flow vector. |
| **Credit stats** | Net leverage, EBITDA/interest and (EBITDA−capex)/interest coverage, and FCF conversion by year — the covenant-style ratios a credit committee actually watches. |
| **Attribution** | The value-creation bridge — (ΔEBITDA × entry multiple) + (Δmultiple × exit EBITDA) + net-debt paydown − all fees — **sums exactly to the equity gain**; the test suite asserts the identity. The ΔEBITDA×Δmultiple cross term sits in the multiple line (the most common convention). |

### Sources consulted

Conventions above were checked against: [Wall Street Prep on financing-fee accounting (ASC 835-30)](https://www.wallstreetprep.com/knowledge/debt-accounting-treatment-financing-fees/), [Macabacus on LBO transaction and financing fees](https://macabacus.com/lbo-model/fees-and-expenses), [Corporate Finance Institute's LBO model and credit-metrics overview](https://corporatefinanceinstitute.com/resources/financial-modeling/lbo-model/), [Street of Walls' LBO modelling test](https://www.streetofwalls.com/finance-training-courses/private-equity-training/lbo-modeling-test-example/), and Wall Street Oasis practitioner threads on [circular references in LBO models](https://www.wallstreetoasis.com/forum/private-equity/circular-references-in-lbo-models) and [fee treatment](https://www.wallstreetoasis.com/forum/private-equity/lbo-model-how-to-treat-transaction-fee-and-financing-fees). Rosenbaum & Pearl, *Investment Banking* (Ch. 5) remains the canonical text for the full build.

## Documented simplifications

Stated openly, because pretending they don't exist is how models lie. These are deliberate: each is either immaterial to a screening-grade answer or would demand deal-specific data the tool doesn't have.

**Accepted, with reasons**

- **Annual periodicity** — real credit agreements amortise and test covenants quarterly. Annual is the standard screening convention; sub-annual timing shifts IRR by tens of basis points, not the answer.
- **Fixed rates** — no SOFR curve or hedging. A floating-rate build needs a rate path assumption that is itself a bigger source of error than the convention.
- **Revenue-driven working capital** — ΔNWC as a % of revenue change, rather than separate DSO/DIO/DPO drivers. The three-driver build is more precise but needs company-specific data.
- **No unamortised-fee write-off** on early repayment (a non-cash P&L item that doesn't touch returns).
- **The exit-equity floor at zero** means the bridge identity holds only for solvent exits — wipeouts are reported as such rather than as negative equity.

**Genuine gaps, and what they'd change**

- **No dividend recapitalisations** — a recap pulls cash forward and materially lifts IRR while leaving MOIC roughly flat. This is the largest missing mechanic for modelling real sponsor behaviour.
- **No management rollover, option pool, or transaction bonuses** — these dilute sponsor proceeds at exit, typically by low-single-digit percentages of equity value.
- **No add-on acquisitions** — buy-and-build is a major value-creation lever the model can't express.
- **Single-company, no segment build** — revenue is one line, not a mix.

Each is a candidate for a later phase; none silently distorts a normal base case, and the guardrail layer flags when inputs drift somewhere the simplifications would start to bite.

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

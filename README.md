# LBO Lab

A deal-level leveraged-buyout model with a web interface. Three layers, deliberately separated:

| Layer | What it is | Why it's separate |
|---|---|---|
| `src/lbo_engine/` | A pure, deterministic Python model. Assumptions in, fully populated model out — no I/O, no state. | The maths is testable in isolation and can never be accidentally coupled to a front end. |
| `api/` | A thin FastAPI transport over the engine. **No financial logic lives here.** | The request contract *is* the engine's own Pydantic model, so the API schema and the model cannot drift apart. |
| `web/` | A React + TypeScript client (Vite, Recharts). | The interface can be rebuilt without touching a single tested calculation. |

The engine has no knowledge of any of this. It was written and tested before either interface existed, and the test suite runs without FastAPI or Node installed at all.

## Running it

```bash
pip install -e ".[dev,api]"
npm install --prefix web
```

Development — two processes, with Vite proxying `/api` to the backend:

```bash
uvicorn api.main:app --reload --port 8000
```

```bash
npm run dev --prefix web
```

Production — one process. FastAPI serves the built SPA, with a catch-all that falls back to `index.html` so client-side routes survive a hard refresh:

```bash
npm run build --prefix web && uvicorn api.main:app --port 8000
```

The interactive API schema is at `/api/docs`.

## Test suite

```bash
pytest
```

136 tests. The engine tests assert the maths (below); the API tests assert the *transport* — that the bridge identity survives serialisation, that NaN and infinity arrive as `null` rather than as invalid JSON or a fabricated number, and that a structure the engine refuses to model returns a describable 422 rather than a 500.

## The case-study library

Four real buyouts, replayed through the same engine: **Hilton** (Blackstone, 2007), **HCA** (KKR/Bain/MLGPE, 2006), **TXU** (KKR/TPG/GS, 2007) and **RJR Nabisco** (KKR, 1989). Two winners, one flat, one total loss — a set of four winners would teach nothing, and a test asserts the spread so a later edit can't quietly turn it into a highlight reel.

Each case is modelled **twice**, on the same capital structure:

| Column | Built from | Answers |
|---|---|---|
| **As signed** | Information available *before close* only — trailing trend, contemporaneous consensus, the banker ranges in the proxy. | What would this model have said at the time? |
| **Actual operating path** | The same structure fed the revenue and margin path that actually occurred. | Does the engine reproduce reality when handed reality? |
| **What happened** | Reported outcome, with a confidence label. | Not a model output, and styled so it can't be mistaken for one. |

Where possible the realised column is **calibrated against reported outcomes and then checked**, not fitted and asserted. HCA is the clearest example: modelled 2010 revenue of $30.3bn against $30.7bn reported, closing debt of $26.2bn against $28.2bn, and exit equity of $18.7bn against an IPO that valued the company near $15.8bn.

Every input carries provenance — **reported** (appears in a filing), **derived** (follows arithmetically), or **estimated** (a judgement call, with the reasoning given). Two tests enforce the no-hindsight claim rather than merely asserting it in prose: one fails if any case underwrites an exit multiple above its entry multiple (the commonest way hindsight smuggles itself in), another fails if the two columns differ in anything but the operating path and the exit.

Three of the eight runs hit a **liquidity break**: operating cash flow stops covering contractual interest and amortisation, and the revolver cannot fund the gap. The engine stops there rather than printing a schedule that quietly runs a negative cash balance — which is what a model without a liquidity constraint does, and why such models never show a deal failing. Each break is reported with the year it happens and a full schedule for the years the structure *did* service, so the drain is legible rather than merely asserted:

- **Hilton's realised path breaks in year three.** Fed the RevPAR collapse that actually happened, cash interest exceeds EBITDA from 2009 and the revolver is exhausted by 2010 — which is precisely when Blackstone bought back ~$2bn of Hilton's debt for ~$800m and converted ~$2bn to preferred. The model identifies the restructuring from the numbers alone.
- **RJR breaks on its own underwriting, in year two.** At the reported 87% debt the modelled cheque lands at $3.9bn against KKR's ~$3.2bn, and cash interest plus PIK accrual then consumes close to the whole of a $3.1bn EBITDA. Historically exact: the deal was never self-financing from operations — it depended on the divestitures clearing, and still needed a $1.7bn equity injection in 1990.
- **TXU underwrites at a low-double-digit IRR** and still lost $8.3bn. Nothing in the guardrails, the tornado or the sensitivity grid flags it, because every one of those varies inputs the model contains — and the input that destroyed the deal, the price of natural gas, was not one of them.

Where the engine structurally cannot follow a deal — RJR's divestitures and preferred layer, HCA's IPO dilution, TXU's gas hedges, Hilton's discounted debt buyback and staged sell-down — it is stated on the page rather than closed by tuning an assumption until the answer looks right.

One of those caveats has since been closed rather than restated. HCA's realised column originally carried "the engine has no recap mechanic"; the engine now has one, and that column models HCA's 2010 dividend recapitalisation sized to the ~$4.3bn actually paid. The case exposed the gap and the gap got fixed — which is the point of building the library before finishing the engine.

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
| **Divestitures** | A business sold mid-hold, proceeds repaying debt senior-first (the mandatory-prepayment waterfall a credit agreement actually requires). Proceeds-only by design: the operating effect of losing the business must be carried in the revenue and margin path, because only the case-builder knows what was sold and what it earned. |
| **PIK toggle** | The issuer's *option* to accrue a coupon rather than pay it, at a step-up — distinct from `pik_rate`, which accrues unconditionally. Elected only when the year cannot otherwise be paid, searched junior-first, because nobody PIKs a coupon they can afford. In 2007 roughly a fifth of buyout firms used toggle debt and 13% of US junk-rated bond sales carried the feature. |
| **Dividend recaps** | Incremental debt raised against the company, proceeds paid to the sponsor. Sized by a **target leverage** (the instruction a sponsor actually gives) or a fixed amount. Treated as a **year-end event**, so the new debt accrues no interest in the year it is raised — it existed for none of it — which also keeps the within-year interest solve to a single circularity. MOIC counts the dividends; the IRR vector receives them in the year they are paid. |
| **Lifecycle** | The same run re-read as a sequence of *events* rather than a table of years: the cheque, each PIK election and what forced it, recaps, first revolver draw, coverage falling through 2.0×, the exit. Derived from a completed run — it is a reading of the model, not a second model. |
| **Attribution** | The value-creation bridge — (ΔEBITDA × entry multiple) + (Δmultiple × exit EBITDA) + net-debt paydown + gross recap debt raised − all fees — **sums exactly to the sponsor's total proceeds** (exit equity plus recap dividends) less the entry cheque; the test suite asserts the identity. The recap line carries **gross** debt raised rather than the net dividend, and that is forced rather than chosen: the net leaves the identity short by exactly the financing fee. The ΔEBITDA×Δmultiple cross term sits in the multiple line (the most common convention). |

### Sources consulted

Conventions above were checked against: [Wall Street Prep on financing-fee accounting (ASC 835-30)](https://www.wallstreetprep.com/knowledge/debt-accounting-treatment-financing-fees/), [Macabacus on LBO transaction and financing fees](https://macabacus.com/lbo-model/fees-and-expenses), [Corporate Finance Institute's LBO model and credit-metrics overview](https://corporatefinanceinstitute.com/resources/financial-modeling/lbo-model/), [Street of Walls' LBO modelling test](https://www.streetofwalls.com/finance-training-courses/private-equity-training/lbo-modeling-test-example/), and Wall Street Oasis practitioner threads on [circular references in LBO models](https://www.wallstreetoasis.com/forum/private-equity/circular-references-in-lbo-models) and [fee treatment](https://www.wallstreetoasis.com/forum/private-equity/lbo-model-how-to-treat-transaction-fee-and-financing-fees). Rosenbaum & Pearl, *Investment Banking* (Ch. 5) remains the canonical text for the full build.

## Why some case-study runs break, and what it measures

Three of eight runs hit a liquidity break, which prompted a fair question: is the model too fragile? Two separate causes turned up, and both were mine rather than the engine's.

**The first was a reconstruction error.** RJR's "as signed" column originally broke in year two, which looked like the model rejecting a deal that demonstrably closed and ran for six years. It was rejecting the *structure* while knowing nothing about the *plan*: KKR underwrote RJR on a sum-of-the-parts, with Del Monte and the European Nabisco businesses earmarked for sale before close. Modelling the capital structure without the divestitures that serviced it describes a deal nobody signed. With them modelled, the column not only survives — it returns **0.85× against a reported ~1.0×**, and a negative IRR against a reported one of well under 1%. The winner's curse was visible at signing.

**The second was missing optionality.** The shortfalls were 3.0–4.8% of enterprise value — near-misses, not catastrophes. Of five levers a distressed deal actually has, one dominated:

| Lever | Hilton | RJR | TXU |
|---|---|---|---|
| Bigger revolver | breaks | survives | breaks |
| Capex cut 30% | breaks | breaks | breaks |
| Burn the cash buffer | breaks | breaks | breaks |
| Defer amortisation | breaks | survives | breaks |
| **PIK toggle** | **survives** | **survives** | breaks |

The engine was asking whether operations could service the contract *as written*. A real contract is renegotiable, and these structures carried explicit options — in 2007 roughly a fifth of buyout firms used toggle debt. A static model is therefore systematically more fragile than reality.

**Where that leaves the library.** No "as signed" column breaks: all four deals model cleanly on pre-close information, which is the correct result, because all four were financeable enough to close. Three *realised* columns break, and each lands on the year the real deal hit its crisis — Hilton in 2010 (the year Blackstone renegotiated), RJR in 1993 (Marlboro Friday), TXU partway to its 2014 filing. The model finds those years without being told about them.

TXU keeps its break under every lever, which is right for the only one of the four that actually filed. Its junior tranche is named "Senior unsecured toggle notes" and had been modelled as pure cash-pay — the right name on the wrong instrument; correcting it halves the shortfall without changing the verdict.

One bias is named rather than fixed: these are four *famous* deals, and deals are famous because they were extreme. Three are peak-vintage. HCA — the one bought at a sane multiple — never breaks in either column.

## Documented simplifications

Stated openly, because pretending they don't exist is how models lie. These are deliberate: each is either immaterial to a screening-grade answer or would demand deal-specific data the tool doesn't have.

**Accepted, with reasons**

- **Annual periodicity** — real credit agreements amortise and test covenants quarterly. Annual is the standard screening convention; sub-annual timing shifts IRR by tens of basis points, not the answer.
- **Fixed rates** — no SOFR curve or hedging. A floating-rate build needs a rate path assumption that is itself a bigger source of error than the convention.
- **Revenue-driven working capital** — ΔNWC as a % of revenue change, rather than separate DSO/DIO/DPO drivers. The three-driver build is more precise but needs company-specific data.
- **No unamortised-fee write-off** on early repayment (a non-cash P&L item that doesn't touch returns).
- **The exit-equity floor at zero** means the bridge identity holds only for solvent exits — wipeouts are reported as such rather than as negative equity.

**Genuine gaps, and what they'd change**

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
  analysis.py       # Sensitivity, tornado, scenarios, credit stats, exit timing, breakeven
  calibration.py    # Market-range guardrails with cited sources
api/
  main.py           # Routes. Granular, so the client pays only for the tab it's viewing
  serialisation.py  # Engine dataclasses → JSON-safe response models (NaN/inf → null)
  presets.py        # Default deal + the preset library
  case_studies.py   # Four real deals: sourced inputs, both columns, caveats, outcomes
web/src/
  api/              # Typed client, abortable + debounced fetch hooks
  components/       # Design-system primitives, charts, tables, the assumptions panel
  routes/           # Landing, Simulator, Cases, CaseStudy
  styles/global.css # The design system in one file
tests/
  conftest.py       # simple_deal (hand-computable golden case) + rich_deal (all features)
  test_engine.py    # Golden-case assertions to 1e-6 + invariants that must hold for any deal
  test_returns.py   # IRR solver against known closed-form answers
  test_api.py       # The transport contract
  test_case_studies.py  # Replay contract + the no-hindsight guards
```

## Interface notes

The client is not a thin wrapper around the endpoints; a few decisions carry weight:

- **`null` is never rendered as zero.** A failed structure, a wiped-out sponsor and infinite coverage all arrive as `null` and render as an em-dash or an empty heat-map cell. A fabricated number in a sensitivity grid is worse than a blank, because it looks like an answer.
- **Guardrail bands are drawn on the sliders**, so you can see that you are dragging out of the market as you do it, rather than being told afterwards.
- **The heat-map ramp is anchored to a fixed hurdle**, not to the range of the data — a relative ramp would repaint the same IRR a different colour as the deal changed, which teaches the eye nothing.
- **Heavy analyses are gated on their tab.** The sensitivity grid is ~25 engine runs; dragging a slider on the Overview tab costs exactly one.
- **The annual schedule is laid out line-items-down, years-across** — the orientation the model would take in Excel — and hides nothing, including the NOL roll-forward and the pass count of the interest solve.

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

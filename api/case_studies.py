"""The case-study library: four real buyouts, replayed through the engine.

The point of this module is not to show that the model can produce a number for
a famous deal. It is to answer a harder question honestly:

    Given only what was knowable at signing, what would this model have said —
    and how much of the eventual outcome was in the numbers at the time?

So every case carries **two** assumption sets built on the same capital
structure:

* ``underwriting`` — reconstructed from information available *before close*.
  Growth, margin and exit-multiple assumptions are set to what a sponsor could
  defensibly have underwritten at the time (consensus, trailing trend, sell-side
  ranges), never to what actually happened. This is the no-hindsight case.
* ``realised`` — the identical structure fed the operating path and exit
  multiple that actually occurred. This is the control: if the engine is sound,
  feeding it reality should reproduce reality.

The gap between the two columns is the deal's *news*. The gap between the
realised column and the reported outcome is the model's *error*, and where that
error has a structural cause — a divestiture, a dividend recap, a preferred
layer the engine has no concept of — it is named in ``model_caveats`` rather
than quietly absorbed into an assumption.

Every input number carries provenance. ``reported`` means it appears in a filing
or a press release; ``derived`` means it follows arithmetically from reported
figures; ``estimated`` means it is a judgement call, and the reasoning is given.
A case study that does not distinguish between those three is a story, not an
analysis.

Figures are in $ millions throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lbo_engine import (
    Assumptions,
    DebtTranche,
    Divestiture,
    DividendRecap,
    OperatingAssumptions,
    RevolverAssumptions,
)

Basis = Literal["reported", "derived", "estimated"]


# --------------------------------------------------------------------- sources

@dataclass(frozen=True)
class Source:
    key: str
    label: str
    url: str


SOURCES: list[Source] = [
    Source(
        "hilton-8k",
        "Hilton Hotels Corp — Form 8-K and merger press release, 3 July 2007",
        "https://www.sec.gov/Archives/edgar/data/0000047580/000110465907052273/a07-18077_18k.htm",
    ),
    Source(
        "hilton-prem14a",
        "Hilton Hotels Corp — Form PREM14A (proxy), 2007. Contains the banker "
        "valuation ranges, incl. implied EV/CY2007E EBITDA of 15.5× on management "
        "projections and 14.5× on street estimates.",
        "https://www.sec.gov/Archives/edgar/data/0000047580/000110465907056667/a07-20270_1prem14a.htm",
    ),
    Source(
        "hilton-oxford",
        "Saïd Business School, University of Oxford — 'Hilton Hotels: Real Estate "
        "Private Equity' teaching case",
        "https://www.sbs.ox.ac.uk/sites/default/files/2018-07/hilton-new-watermark.pdf",
    ),
    Source(
        "hilton-bsic",
        "Bocconi Students Investment Club — 'The Best Leveraged Buyout Ever: "
        "Blackstone × Hilton'",
        "https://bsic.it/vintage-private-equity-the-best-leveraged-buyout-ever-blackstone-x-hilton/",
    ),
    Source(
        "hca-8k",
        "HCA Inc. — Form 8-K, merger agreement announcement, 24 July 2006",
        "https://www.sec.gov/Archives/edgar/data/860730/000095014406006852/g02483exv99w2.txt",
    ),
    Source(
        "hca-close",
        "HCA Healthcare — 'HCA Completes Merger With Private Investor Group', "
        "17 November 2006",
        "https://investor.hcahealthcare.com/news/news-details/2006/HCA-Completes-Merger-With-Private-Investor-Group/default.aspx",
    ),
    Source(
        "hca-fortune",
        "Fortune — 'Before & After: HCA by the numbers', March 2011",
        "https://fortune.com/2011/03/08/before-after-hca-by-the-numbers/",
    ),
    Source(
        "txu-bsic",
        "Bocconi Students Investment Club — 'TXU: Learnings from the Largest LBO "
        "(Bust) in History'",
        "https://bsic.it/vintage-private-equity-deals-txu-learnings-from-the-largest-lbo-bust-in-history/",
    ),
    Source(
        "txu-efh-bankruptcy",
        "Pachulski Stang Ziehl & Jones — Energy Future Holdings Chapter 11 case "
        "record, filed 29 April 2014",
        "https://www.pszjlaw.com/case/energy-future-holdings/",
    ),
    Source(
        "rjr-wapo",
        "The Washington Post — 'Now, the Big Question Is Did KKR Pay Too Much?', "
        "3 December 1988",
        "https://www.washingtonpost.com/archive/business/1988/12/03/now-the-big-question-is-did-kkr-pay-too-much/00ceee52-80a4-4274-aea9-e5f9d739c5a2/",
    ),
    Source(
        "rjr-10k94",
        "RJR Nabisco Inc. — Form 10-K for FY1994",
        "http://getfilings.com/o0000950112-95-000460.html",
    ),
    Source(
        "barbarians",
        "Burrough & Helyar, *Barbarians at the Gate* (1990) — the standard "
        "narrative account of the auction and the final structure.",
        "https://en.wikipedia.org/wiki/Barbarians_at_the_Gate",
    ),
]


# ------------------------------------------------------------------ provenance

@dataclass(frozen=True)
class Figure:
    """One input, with the reason it holds the value it does."""

    label: str
    value: str
    basis: Basis
    note: str
    source: str | None = None


@dataclass(frozen=True)
class Outcome:
    """What actually happened. Deliberately separate from the assumptions so it
    is impossible for an outcome figure to leak into an underwriting input."""

    exit_route: str
    exit_year: int
    holding_years: float
    realised_moic: float | None
    realised_irr: float | None
    confidence: Literal["reported", "widely reported", "estimated", "disputed"]
    headline: str
    narrative: str


@dataclass(frozen=True)
class CaseStudy:
    slug: str
    name: str
    sponsor: str
    signed: str
    closed: str
    sector: str
    verdict: Literal["home run", "solid", "flat", "wipeout"]
    # The one-line reason this deal is in the library at all.
    why_it_is_here: str
    thesis: str
    could_not_have_known: str
    underwriting: Assumptions
    realised: Assumptions | None
    provenance: list[Figure]
    model_caveats: list[str]
    outcome: Outcome
    source_keys: list[str] = field(default_factory=list)
    # Read *before* the numbers, keyed "underwriting" / "realised". Present when
    # a column needs interpreting rather than merely reading — most importantly
    # when the engine refuses to model the structure, which in this library is
    # usually the finding rather than a defect.
    column_notes: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------- Hilton
# Blackstone's real-estate and corporate PE funds, $26bn, signed July 2007 and
# closed that October — the last of the mega-LBOs before the window shut.

_HILTON_EBITDA = 1749.0  # 2006A adjusted EBITDA
_HILTON_REVENUE = 8162.0  # 2006A revenue

HILTON = CaseStudy(
    slug="hilton-blackstone-2007",
    name="Hilton Hotels",
    sponsor="The Blackstone Group",
    signed="3 July 2007",
    closed="24 October 2007",
    sector="Lodging",
    verdict="home run",
    why_it_is_here=(
        "The single best answer to 'you overpaid'. Blackstone bought at the top of "
        "the cycle, at a multiple the guardrails in this app flag as out of range, "
        "into the worst lodging downturn since the war — and still made about $14bn. "
        "If entry multiple were destiny, this deal would be a crater."
    ),
    thesis=(
        "Hilton was two businesses stapled together: a large owned real-estate "
        "portfolio and an under-exploited global brand. The underwriting case was "
        "to expand the managed and franchised estate aggressively outside the US — "
        "capital-light fee income against an owned portfolio that could be sold "
        "down — while running the owned hotels harder. RevPAR had compounded through "
        "2004–2007 and the sell-side consensus into 2008 was for continued mid-single-"
        "digit growth. Debt was raised almost entirely as property-secured mortgage "
        "and mezzanine paper, with no maintenance covenants and no meaningful "
        "amortisation, at the peak of a lending market that would not exist six months "
        "later."
    ),
    could_not_have_known=(
        "That the CMBS market would close within weeks of the deal closing, that US "
        "RevPAR would fall roughly 17% in 2009, and that the hold would run eleven "
        "years rather than the five a 2007 underwriting model would have assumed. "
        "Equally: that the covenant-lite, no-amortisation structure they had just "
        "signed — an artefact of frothy credit, not of foresight — was precisely what "
        "would let the company survive the fall in cash flow without a default."
    ),
    underwriting=Assumptions(
        entry_ebitda=_HILTON_EBITDA,
        entry_multiple=14.87,  # $26.0bn / $1,749m 2006A
        operating=OperatingAssumptions(
            entry_revenue=_HILTON_REVENUE,
            revenue_growth=0.06,
            ebitda_margin=[0.214, 0.221, 0.228, 0.234, 0.240],
            da_pct_revenue=0.075,
            capex_pct_revenue=0.070,
            nwc_pct_revenue=0.03,
            tax_rate=0.38,
        ),
        tranches=[
            DebtTranche(
                name="Senior mortgage (CMBS)",
                leverage_turns=4.35,  # ~$7.6bn
                cash_rate=0.0675,
                mandatory_amort_pct=0.0,  # interest-only, as signed
                sweepable=True,
            ),
            DebtTranche(
                name="Second-lien notes",
                leverage_turns=0.57,  # ~$1.0bn
                cash_rate=0.0775,
                sweepable=True,
            ),
            DebtTranche(
                name="Mezzanine loans I–III",
                leverage_turns=6.80,  # ~$11.9bn
                cash_rate=0.0850,
                sweepable=False,
            ),
        ],
        revolver=RevolverAssumptions(commitment=1000.0, cash_rate=0.0725, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.010,
        financing_fee_pct_debt=0.020,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,  # pre-TCJA: no 80% limitation, full carryforward
        minimum_cash=300.0,
        cash_sweep_pct=0.75,
        hold_years=5,
        exit_multiple=14.0,
    ),
    realised=Assumptions(
        entry_ebitda=_HILTON_EBITDA,
        entry_multiple=14.87,
        operating=OperatingAssumptions(
            entry_revenue=_HILTON_REVENUE,
            # 2008 flat, 2009 collapse, slow recovery, then a long expansion.
            revenue_growth=[0.02, -0.17, -0.06, 0.09, 0.08, 0.06, 0.05, 0.05, 0.04, 0.04, 0.05],
            # The asset-light shift: margin expanded materially over the hold.
            ebitda_margin=[
                0.214, 0.196, 0.190, 0.205, 0.218, 0.232, 0.244,
                0.252, 0.258, 0.264, 0.270,
            ],
            da_pct_revenue=0.075,
            capex_pct_revenue=0.055,
            nwc_pct_revenue=0.03,
            tax_rate=0.38,
        ),
        tranches=[
            DebtTranche(name="Senior mortgage (CMBS)", leverage_turns=4.35, cash_rate=0.0675, sweepable=True),
            DebtTranche(name="Second-lien notes", leverage_turns=0.57, cash_rate=0.0775, sweepable=True),
            DebtTranche(name="Mezzanine loans I–III", leverage_turns=6.80, cash_rate=0.0850, sweepable=False),
        ],
        revolver=RevolverAssumptions(commitment=1000.0, cash_rate=0.0725, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.010,
        financing_fee_pct_debt=0.020,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=300.0,
        cash_sweep_pct=0.75,
        hold_years=11,
        exit_multiple=13.5,
    ),
    provenance=[
        Figure("Enterprise value", "$26.0bn", "reported",
               "All-cash merger at $47.50 per share, a ~40% premium. Announced 3 July 2007.",
               "hilton-8k"),
        Figure("Entry EBITDA", "$1,749m", "reported",
               "2006A adjusted EBITDA. Used as the LTM base rather than a forward "
               "figure, so the entry multiple is struck on money the company had "
               "actually earned.", "hilton-oxford"),
        Figure("Entry multiple", "14.9×", "derived",
               "$26.0bn ÷ $1,749m. The proxy's own bankers put it at 15.5× CY2007E on "
               "management projections and 14.5× on street estimates — the LTM figure "
               "sits between them, which is the reassurance that the base is right.",
               "hilton-prem14a"),
        Figure("Debt / equity", "$20.5bn / $5.6bn", "reported",
               "78.5% debt. Split here as ~$7.6bn senior mortgage, ~$1.0bn second lien "
               "and ~$11.9bn mezzanine I–III.", "hilton-bsic"),
        Figure("Amortisation", "None", "reported",
               "Property-level mortgage and mezzanine paper, interest-only. This is not "
               "a modelling simplification — the absence of amortisation is the reason "
               "the structure survived 2009.", "hilton-bsic"),
        Figure("Revenue growth (underwriting)", "6.0% p.a.", "estimated",
               "Set to the trailing 2004–2007 lodging RevPAR trend and 2007 sell-side "
               "consensus for 2008. Deliberately not informed by what followed."),
        Figure("Margin path (underwriting)", "21.4% → 24.0%", "estimated",
               "The stated thesis was international unit growth in managed and franchised "
               "formats, which carry higher incremental margin. 260bps over five years is "
               "a defensible sponsor case, not an aggressive one."),
        Figure("Exit multiple (underwriting)", "14.0×", "estimated",
               "Slightly below entry. Underwriting flat-to-down on the multiple was "
               "standard practice even in 2007; assuming expansion off a 14.9× entry "
               "would not have cleared an investment committee."),
        Figure("Realised operating path", "2009 revenue −17%", "reported",
               "US RevPAR fell roughly 17% in 2009. The realised column uses that path "
               "and the margin expansion Hilton actually delivered through the "
               "asset-light shift.", "hilton-bsic"),
    ],
    model_caveats=[
        "Blackstone bought back roughly $2bn of Hilton's own debt for about $800m in "
        "2010 and converted a further ~$2bn to preferred. That deleveraging at a "
        "discount is a material part of the return and the engine has no mechanic for "
        "it — the realised column therefore carries more debt through the back half of "
        "the hold than Hilton actually did, and understates the outcome.",
        "The exit was a staged sell-down — a December 2013 IPO followed by four years "
        "of secondary sales through 2018 — not a single liquidity event. The model "
        "exits in one block at the end of the hold, which flatters IRR relative to a "
        "sell-down and understates it relative to an early partial return of capital.",
        "Hilton's owned real estate was carried and financed at the property level. "
        "The engine models one consolidated entity, so it cannot express asset sales "
        "or the spin-offs (Park Hotels, Hilton Grand Vacations) that completed in 2017.",
    ],
    outcome=Outcome(
        exit_route="December 2013 IPO at $20/share, then staged secondary sales to full exit in 2018",
        exit_year=2018,
        holding_years=11.0,
        realised_moic=3.0,
        realised_irr=0.15,
        confidence="widely reported",
        headline="~$14bn of profit — the largest dollar gain in private-equity history",
        narrative=(
            "Blackstone wrote the investment down by around 71% at the trough. Bloomberg's "
            "eventual description — badly timed but brilliantly executed — is exactly "
            "right, and the two halves of it are separable. The timing was as bad as "
            "timing gets. What saved it was structure (no amortisation, no maintenance "
            "covenants, long tenor), operational change under Chris Nassetta, and the "
            "willingness to hold for eleven years instead of five. MOIC of about 3× over "
            "that period is a mid-teens IRR: an outstanding dollar outcome and a merely "
            "good annualised one, which is the distinction the exit-timing chart in this "
            "app exists to make."
        ),
    ),
    source_keys=["hilton-8k", "hilton-prem14a", "hilton-oxford", "hilton-bsic"],
    column_notes={
        "underwriting": (
            "Note how thin this is even on the sponsor's own case: cash interest of "
            "roughly $1.6bn against $1.75bn of entry EBITDA is barely 1.1× coverage "
            "before anything goes wrong. The underwritten return depends on growth "
            "arriving on schedule, with essentially no margin for it not to."
        ),
        "realised": (
            "The structure as signed fails in year three, and this is the most useful "
            "output in the library — because it is right. Fed the RevPAR collapse that "
            "actually happened, cash interest exceeds EBITDA from 2009 and the $1bn "
            "revolver is exhausted by 2010. That is precisely when Blackstone "
            "renegotiated: buying back roughly $2bn of Hilton's own debt for about "
            "$800m and converting a further ~$2bn to preferred. The model is not "
            "failing to describe the deal — it is identifying, from the numbers alone, "
            "the moment the deal had to be restructured to survive. What follows "
            "afterwards is a different capital structure, and this engine has no "
            "mechanic for the change."
        ),
    },
)


# ------------------------------------------------------------------------- HCA
# The largest LBO in history at the time of closing, and the one that worked.

_HCA_EBITDA = 4300.0   # 2005A adjusted EBITDA
_HCA_REVENUE = 24455.0  # 2005A revenue

HCA = CaseStudy(
    slug="hca-kkr-bain-2006",
    name="HCA",
    sponsor="KKR, Bain Capital, Merrill Lynch Global Private Equity & the Frist family",
    signed="24 July 2006",
    closed="17 November 2006",
    sector="Hospitals / healthcare facilities",
    verdict="solid",
    why_it_is_here=(
        "The control case. Same vintage window as Hilton and TXU, similar scale, and "
        "it simply worked — because it was bought at a defensible multiple on cash "
        "flows that are close to non-cyclical. It is the deal that shows how much of "
        "the 2006–07 record is entry price and sector, not sponsor brilliance."
    ),
    thesis=(
        "A take-private of the largest US hospital operator, at a mid-to-high single-"
        "digit multiple, alongside the founding family. The case was not growth: it "
        "was that hospital admissions are close to inelastic, that HCA's scale gave it "
        "pricing leverage with commercial payors, and that a business converting "
        "revenue to cash this reliably could carry six and a half turns without ever "
        "coming near a covenant. Capex is heavy and non-negotiable in hospitals, which "
        "caps the sweep — so the return had to come from EBITDA growth and paydown "
        "rather than from multiple expansion."
    ),
    could_not_have_known=(
        "The 2010 Affordable Care Act, which expanded insurance coverage and cut "
        "uncompensated care — a direct tailwind to exactly the line the underwriting "
        "case was most exposed on. Also unknowable: that the credit markets would "
        "reopen far enough by 2010 to fund several billion dollars of dividend "
        "recapitalisation years before the IPO."
    ),
    underwriting=Assumptions(
        entry_ebitda=_HCA_EBITDA,
        entry_multiple=7.67,  # $33.0bn / $4,300m
        operating=OperatingAssumptions(
            entry_revenue=_HCA_REVENUE,
            revenue_growth=0.06,
            ebitda_margin=0.176,
            da_pct_revenue=0.052,
            capex_pct_revenue=0.062,
            nwc_pct_revenue=0.08,
            tax_rate=0.38,
        ),
        tranches=[
            DebtTranche(
                name="Senior secured term loans",
                leverage_turns=3.91,  # ~$16.8bn
                cash_rate=0.0750,
                mandatory_amort_pct=0.01,
                sweepable=True,
            ),
            DebtTranche(
                name="Second-lien secured notes",
                leverage_turns=1.33,  # ~$5.7bn
                cash_rate=0.0925,
                sweepable=True,
            ),
            DebtTranche(
                name="Senior unsecured notes",
                leverage_turns=1.28,  # ~$5.5bn
                cash_rate=0.0963,
                sweepable=False,
            ),
        ],
        revolver=RevolverAssumptions(commitment=2000.0, cash_rate=0.0750, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.010,
        financing_fee_pct_debt=0.020,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=400.0,
        cash_sweep_pct=0.75,
        hold_years=5,
        exit_multiple=7.5,
    ),
    realised=Assumptions(
        entry_ebitda=_HCA_EBITDA,
        entry_multiple=7.67,
        operating=OperatingAssumptions(
            entry_revenue=_HCA_REVENUE,
            # Calibrated to two reported points: revenue of $24,455m in 2005 and
            # $30,683m in 2010. The path between them is the plausible shape, but
            # the endpoint is not a guess — it is the figure Fortune published.
            revenue_growth=[0.08, 0.05, 0.03, 0.02, 0.041],
            ebitda_margin=[0.176, 0.178, 0.181, 0.185, 0.192],
            da_pct_revenue=0.048,
            capex_pct_revenue=0.058,
            nwc_pct_revenue=0.08,
            tax_rate=0.38,
        ),
        tranches=[
            DebtTranche(name="Senior secured term loans", leverage_turns=3.91, cash_rate=0.0750,
                        mandatory_amort_pct=0.01, sweepable=True),
            DebtTranche(name="Second-lien secured notes", leverage_turns=1.33, cash_rate=0.0925, sweepable=True),
            DebtTranche(name="Senior unsecured notes", leverage_turns=1.28, cash_rate=0.0963, sweepable=False),
        ],
        revolver=RevolverAssumptions(commitment=2000.0, cash_rate=0.0750, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.010,
        financing_fee_pct_debt=0.020,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=400.0,
        # HCA did not sweep. Free cash flow went to capex and, from 2010, to
        # dividend recapitalisations — reported debt was still $28.2bn in 2010
        # against $28bn at close. Running a 75% sweep here would deleverage a
        # company that in reality never deleveraged, and would inflate terminal
        # equity accordingly. A 25% sweep reproduces the actual debt path.
        cash_sweep_pct=0.25,
        # The 2010 recapitalisations, sized to the ~$4.3bn HCA actually paid out
        # that year. Year 4 of a hold that closed in November 2006 is 2010.
        recaps=[DividendRecap(year=4, amount=4300.0, financing_fee_pct=0.02)],
        # Exit at the March 2011 IPO rather than at the 2016 full exit. The IPO is
        # a real, dated liquidity event with an observable equity value, so the
        # comparison is like-for-like. Running to 2016 compares a whole-equity
        # single-exit MOIC against a sponsor return that was diluted at the IPO
        # and then sold down over five years — two different measurements.
        hold_years=5,
        exit_multiple=7.5,
    ),
    provenance=[
        Figure("Enterprise value", "$33.0bn", "reported",
               "Approximately $21.3bn of cash consideration plus $11.7bn of debt "
               "assumed or repaid. The largest LBO ever at the time of closing.",
               "hca-8k"),
        Figure("Entry EBITDA", "$4,300m", "estimated",
               "2005A adjusted EBITDA against reported 2005 revenue of $24,455m — a "
               "17.6% margin, consistent with HCA's reported operating performance. "
               "Treated as estimated rather than reported because the adjustment "
               "basis in the deal model is not public.", "hca-fortune"),
        Figure("Entry multiple", "7.7×", "derived",
               "$33.0bn ÷ $4,300m. Note how far below Hilton's 14.9× this sits: the "
               "same vintage, half the price."),
        Figure("Sponsor equity", "$5.3bn", "reported",
               "KKR, Bain, Merrill Lynch Global Private Equity and the Frist family.",
               "hca-fortune"),
        Figure("Leverage", "~6.5×", "derived",
               "~$28bn of debt against $4,300m of EBITDA. High in absolute terms, but "
               "carried by cash flows with very little cyclicality."),
        Figure("Capex", "6.2% of revenue", "estimated",
               "Hospital maintenance and expansion capex is heavy and cannot be "
               "deferred. Setting this correctly matters more here than in any other "
               "case in the library, because it is what limits the sweep."),
        Figure("Realised revenue path", "$24.5bn → $30.7bn by 2010", "reported",
               "Reported revenue before and after. The realised column is fitted to "
               "these two points with a plausible path between them.", "hca-fortune"),
    ],
    model_caveats=[
        "The recapitalisation is modelled as a single year-four event, but HCA's actual "
        "payouts were staged across 2010 and beyond. Compressing them into one date "
        "slightly overstates IRR, because part of that cash genuinely arrived later.",
        "Modelled 2010 debt overshoots the reported figure by roughly $2.9bn once the "
        "full dividend is paid — see the column note. The dividend total is the better-"
        "sourced of the two facts, so it is the one the model is calibrated to.",
        "The sponsors were diluted at the IPO and did not own 100% of the equity "
        "modelled here. Exiting at the IPO date keeps the comparison honest, but the "
        "modelled exit equity is a whole-company figure and the reported multiple is a "
        "sponsor-share one.",
        "The reported ~3.5× is quoted in a range across sources rather than disclosed, "
        "and is marked estimated for that reason. The shape of the outcome is not in "
        "doubt; the second decimal place is not available to anyone outside the funds.",
        "The 2005A EBITDA base is an estimate. Every derived figure — entry multiple, "
        "leverage turns, tranche sizing — scales with it, so treat the level as "
        "approximate and the relationships as sound.",
    ],
    outcome=Outcome(
        exit_route="March 2011 IPO (then the largest PE-backed IPO in US history), plus dividend recapitalisations from 2010; full exit by 2016",
        exit_year=2016,
        holding_years=10.0,
        realised_moic=3.5,
        realised_irr=0.20,
        confidence="estimated",
        headline="Roughly 3.5× on $5.3bn, with much of it returned early through recaps",
        narrative=(
            "The least dramatic deal in this library and the most instructive. HCA was "
            "bought at 7.7× — half of what Blackstone paid for Hilton the following year "
            "— on cash flows that barely notice a recession. Nothing clever had to happen: "
            "EBITDA grew, debt was serviced, and the credit markets reopened in time to "
            "pull capital forward through recaps. The Affordable Care Act was a genuine "
            "windfall the underwriting case did not contain. The headline multiple is "
            "widely quoted in a range and should be read as approximate; the shape of the "
            "outcome is not in doubt."
        ),
    ),
    source_keys=["hca-8k", "hca-close", "hca-fortune"],
    column_notes={
        "underwriting": (
            "The only case in the library that clears comfortably on its own "
            "underwriting, and it does so without needing anything clever: coverage "
            "never gets tight, the sweep works, and the return comes from EBITDA "
            "growth and paydown rather than from the exit multiple."
        ),
        "realised": (
            "This column exits at the March 2011 IPO rather than at the 2016 full "
            "exit, and the choice matters. The IPO is a dated event with an observable "
            "equity value, so the comparison is like-for-like; running to 2016 would "
            "compare a whole-equity single-exit MOIC against a sponsor return that was "
            "diluted at the IPO and then sold down over five years, which are two "
            "different measurements. It also now carries HCA's 2010 dividend "
            "recapitalisation, sized to the ~$4.3bn actually paid — the mechanic this "
            "case originally existed to flag as missing. "
            "Two outputs can be checked rather than taken on trust: modelled 2010 "
            "revenue of about $30.3bn against $30.7bn reported, and exit equity of "
            "roughly $14.2bn against an IPO that valued the company near $15.8bn. "
            "One cannot: modelled 2010 debt lands at $31.1bn against $28.2bn reported. "
            "The model can match the reported dividends or the reported debt but not "
            "both, and the gap is informative rather than embarrassing — it says this "
            "operating path generates slightly less debt capacity than HCA actually "
            "had, so the margin assumptions here are mildly conservative."
        ),
    },
)


# ------------------------------------------------------------------------- TXU
# The largest LBO ever attempted, and the largest loss.

_TXU_EBITDA = 5200.0    # 2006A, implied by the reported 8.5× on a $44.3bn EV
_TXU_REVENUE = 10856.0  # 2006A revenue

TXU = CaseStudy(
    slug="txu-kkr-tpg-2007",
    name="TXU Corp. (Energy Future Holdings)",
    sponsor="KKR, TPG & Goldman Sachs Capital Partners",
    signed="26 February 2007",
    closed="10 October 2007",
    sector="Merchant power generation & retail electricity",
    verdict="wipeout",
    why_it_is_here=(
        "The most important case in the library, because the underwriting was not "
        "obviously reckless. TXU was bought at 8.5× — below Hilton, barely above HCA — "
        "with less leverage than either. Run the model on the numbers as signed and it "
        "produces a perfectly respectable return. The deal was destroyed by a single "
        "assumption sitting outside the model entirely: the price of natural gas."
    ),
    thesis=(
        "TXU's generation fleet was largely coal and nuclear, but wholesale power prices "
        "in ERCOT are set at the margin by gas-fired plants. So every dollar of gas price "
        "dropped almost directly into TXU's gross margin — a spread business dressed as a "
        "utility. With gas trading in the $7–9/MMBtu range and forward curves supporting "
        "power in the mid-$60s per MWh, the sponsors underwrote a stable, inflation-plus "
        "cash flow able to carry roughly seven turns. On the numbers as signed, it "
        "clears comfortably. The entire deal was a levered long position on natural gas, "
        "and it was not presented as one."
    ),
    could_not_have_known=(
        "That horizontal drilling and hydraulic fracturing would move from marginal to "
        "dominant within four years, collapsing US gas prices from the $7–9 range to "
        "$2–4 and taking ERCOT power with them — North Texas settled around $40/MWh "
        "against the mid-$60s in the investment case. This was a technology shock, not a "
        "business-cycle one, and nothing in a 2007 forward curve or sell-side model "
        "anticipated it. What *was* knowable, and is the fair criticism: that the "
        "sensitivity of equity value to a single commodity was extreme, and that seven "
        "turns is a great deal of leverage to put on a spread."
    ),
    underwriting=Assumptions(
        entry_ebitda=_TXU_EBITDA,
        entry_multiple=8.52,  # $44.3bn / $5,200m
        operating=OperatingAssumptions(
            entry_revenue=_TXU_REVENUE,
            revenue_growth=0.03,
            ebitda_margin=0.479,
            da_pct_revenue=0.115,
            capex_pct_revenue=0.140,  # heavy: the Oak Grove & Sandow build-out
            nwc_pct_revenue=0.05,
            tax_rate=0.35,
        ),
        tranches=[
            DebtTranche(
                name="Senior secured term loan B",
                leverage_turns=4.71,  # ~$24.5bn
                cash_rate=0.0800,
                mandatory_amort_pct=0.01,
                sweepable=True,
            ),
            DebtTranche(
                name="Senior unsecured toggle notes",
                leverage_turns=2.16,  # ~$11.25bn
                cash_rate=0.1025,
                # These were toggle notes in fact as well as in name: EFH could
                # elect to PIK the coupon rather than pay it, at a step-up. An
                # earlier version of this case modelled them as pure cash-pay,
                # which removed the single most important option the structure
                # actually had.
                pik_toggle=True,
                pik_toggle_premium=0.0075,
                sweepable=False,
            ),
        ],
        revolver=RevolverAssumptions(commitment=2700.0, cash_rate=0.0800, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.010,
        financing_fee_pct_debt=0.025,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=1000.0,
        cash_sweep_pct=0.75,
        hold_years=5,
        exit_multiple=8.5,
    ),
    realised=Assumptions(
        entry_ebitda=_TXU_EBITDA,
        entry_multiple=8.52,
        operating=OperatingAssumptions(
            entry_revenue=_TXU_REVENUE,
            # The shale collapse, year by year through to the 2014 filing.
            revenue_growth=[0.01, -0.10, -0.09, -0.10, -0.08, -0.06, -0.04],
            # Spread compression is far more violent than the revenue line suggests,
            # because the cost base is largely fixed. The first two years hold up
            # because the sponsors' gas hedges were still in the money; the damage
            # lands when they roll off.
            ebitda_margin=[0.472, 0.462, 0.425, 0.370, 0.315, 0.270, 0.235],
            da_pct_revenue=0.130,
            capex_pct_revenue=0.140,
            nwc_pct_revenue=0.05,
            tax_rate=0.35,
        ),
        tranches=[
            DebtTranche(name="Senior secured term loan B", leverage_turns=4.71, cash_rate=0.0800,
                        mandatory_amort_pct=0.01, sweepable=True),
            DebtTranche(name="Senior unsecured toggle notes", leverage_turns=2.16, cash_rate=0.1025,
                        pik_toggle=True, pik_toggle_premium=0.0075, sweepable=False),
        ],
        revolver=RevolverAssumptions(commitment=2700.0, cash_rate=0.0800, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.010,
        financing_fee_pct_debt=0.025,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=1000.0,
        cash_sweep_pct=0.75,
        hold_years=7,
        exit_multiple=6.0,
    ),
    provenance=[
        Figure("Enterprise value", "$44.3bn", "reported",
               "$69.25 per share in cash, a ~25% premium to the 20-day average. The "
               "largest leveraged buyout ever attempted.", "txu-bsic"),
        Figure("Entry multiple", "8.5×", "reported",
               "Against a utility-sector average of 7.9× and a Morgan Stanley / "
               "Blackstone valuation range of 8–13×. By the standards of 2007 this was "
               "a *cheap* deal.", "txu-bsic"),
        Figure("Entry EBITDA", "$5,200m", "derived",
               "Implied by $44.3bn ÷ 8.5×. Note the tension: the same source reports "
               "2006 net EBITDA of ~$4.0bn, which against the same EV would give 11.1×. "
               "The gap is almost certainly adjusted-versus-net and forward-versus-"
               "trailing. The reported multiple is used as the anchor and the EBITDA "
               "backed out of it, because the multiple is the figure the market "
               "actually transacted on — but the discrepancy is real and is why this "
               "figure is marked derived.", "txu-bsic"),
        Figure("Debt / equity", "$36bn / $8.3bn", "reported",
               "$24.5bn senior secured term loans and $11.25bn of senior unsecured "
               "bridge, later termed out as toggle notes.", "txu-bsic"),
        Figure("Power price assumption", "mid-$60s /MWh", "reported",
               "The level underpinning the investment case. North Texas actually "
               "settled around $40/MWh.", "txu-bsic"),
        Figure("Capex", "14% of revenue", "estimated",
               "TXU was mid-way through the Oak Grove and Sandow lignite build-out. "
               "Heavy committed capex on a collapsing top line is what converts a bad "
               "year into a default."),
        Figure("Realised margin path", "47% → 24%", "estimated",
               "Fitted to reproduce the reported outcome: roughly $35bn of debt "
               "outstanding and unserviceable by the April 2014 filing. Marked "
               "estimated because segment-level merchant margins through the period "
               "are not cleanly public.", "txu-efh-bankruptcy"),
    ],
    model_caveats=[
        "The engine models an operating company, not a commodity book. TXU ran a large "
        "hedging programme — the sponsors bought gas hedges precisely against this risk — "
        "which delayed the damage by roughly two years before rolling off into a much "
        "worse market. The realised column compresses margin smoothly and so cannot "
        "reproduce the cliff shape the hedges actually produced.",
        "Energy Future Holdings was a multi-entity structure (TCEH, Oncor, EFIH) with "
        "ring-fenced regulated assets. Oncor retained real value and was eventually sold "
        "to Sempra; the wipeout was concentrated in the merchant side. A single-entity "
        "model necessarily overstates the cleanliness of the loss.",
        "There were several distressed exchanges and liability-management exercises "
        "before the filing. The engine has no restructuring mechanic — it either "
        "services the debt or reports that it cannot.",
    ],
    outcome=Outcome(
        exit_route="Chapter 11 filing, 29 April 2014",
        exit_year=2014,
        holding_years=6.6,
        realised_moic=0.0,
        realised_irr=-1.0,
        confidence="reported",
        headline="$8.3bn of sponsor equity wiped out — the largest loss in private-equity history",
        narrative=(
            "Seven years after close, EFH filed with roughly $42bn of debt against a "
            "business whose merchant margin had collapsed with the price of gas. The "
            "sponsors' equity went to zero. What makes it worth modelling rather than "
            "simply retelling is that the deal does not look like a disaster on the "
            "numbers as signed — the underwriting column in this app is a perfectly "
            "acceptable return. Everything that mattered lived in one input the model "
            "cannot see. That is the durable lesson: sensitivity analysis on the "
            "assumptions inside your model is not risk management if the real exposure "
            "is to something that is not an input."
        ),
    ),
    source_keys=["txu-bsic", "txu-efh-bankruptcy"],
    column_notes={
        "underwriting": (
            "This is the column worth sitting with. On the numbers as signed the deal "
            "returns something respectable — a low-double-digit IRR at under seven "
            "turns, bought more cheaply than Hilton. Nothing in the guardrails, the "
            "tornado or the sensitivity grid flags it, because every one of those "
            "tools varies inputs the model contains, and the input that destroyed this "
            "deal was not one of them."
        ),
        "realised": (
            "Fed the collapse in merchant margin, the structure fails partway through "
            "the hold. The real filing came in April 2014, later than the model's "
            "break, and the difference is the hedging programme: the sponsors had "
            "bought gas hedges that held the damage off for roughly two years before "
            "rolling into a far worse market. The engine has no commodity book, so it "
            "compresses margin smoothly and arrives early. Direction and cause are "
            "right; the timing is approximate, and the reason is named rather than "
            "tuned away."
        ),
    },
)


# ---------------------------------------------------------------- RJR Nabisco
# The deal that named the asset class.

_RJR_EBITDA = 3100.0    # FY1988
_RJR_REVENUE = 16956.0  # FY1988 net sales

RJR = CaseStudy(
    slug="rjr-nabisco-kkr-1989",
    name="RJR Nabisco",
    sponsor="Kohlberg Kravis Roberts & Co.",
    signed="30 November 1988",
    closed="28 April 1989",
    sector="Tobacco & packaged food",
    verdict="flat",
    why_it_is_here=(
        "The deal that created the genre, and the one whose returns almost nobody "
        "remembers correctly. The auction is famous; the outcome — six years of work "
        "for an IRR reported at well under 1% — is not. It is also the cleanest "
        "example of winner's curse in the record."
    ),
    thesis=(
        "Two businesses that should never have been merged. Tobacco threw off "
        "extraordinary cash at very high margins; the Nabisco food brands were good "
        "assets trapped inside a conglomerate discount. The plan was to use tobacco "
        "cash flow to service the debt while selling food businesses to repay principal "
        "quickly — Del Monte and the European Nabisco operations were earmarked before "
        "close. The strategic logic was sound. The price was not: after a contested "
        "auction against the management group, KKR paid $109 a share against a $56 "
        "pre-bid price, and won by bidding more than anyone else would."
    ),
    could_not_have_known=(
        "Marlboro Friday — 2 April 1993 — when Philip Morris cut Marlboro's price by "
        "20% and detonated the premium-cigarette economics the whole structure rested "
        "on. And the escalation of tobacco litigation through the early 1990s, which "
        "compressed the multiple any acquirer would pay for a tobacco business. What "
        "*was* knowable: that the reset provisions on the PIK securities would force a "
        "refinancing if the equity story wobbled. It did, and in 1990 KKR had to inject "
        "about $1.7bn of fresh equity to avoid a default."
    ),
    underwriting=Assumptions(
        entry_ebitda=_RJR_EBITDA,
        entry_multiple=9.71,  # ~$30.1bn total transaction value
        operating=OperatingAssumptions(
            entry_revenue=_RJR_REVENUE,
            # The plan as underwritten: the food businesses leave in the first
            # two years, so revenue falls hard and margin rises because what
            # remains is tobacco. Modelling +5% growth here — as an earlier
            # version did — describes a company KKR never intended to own.
            revenue_growth=[-0.14, -0.11, 0.04, 0.05, 0.05],
            ebitda_margin=[0.190, 0.205, 0.215, 0.220, 0.225],
            da_pct_revenue=0.040,
            capex_pct_revenue=0.045,
            nwc_pct_revenue=0.12,
            tax_rate=0.38,
        ),
        tranches=[
            DebtTranche(
                name="Senior secured bank facilities",
                leverage_turns=4.68,  # ~$14.5bn
                cash_rate=0.1150,     # prime was ~11% in 1989
                mandatory_amort_pct=0.08,
                sweepable=True,
            ),
            DebtTranche(
                name="Subordinated / increasing-rate notes",
                leverage_turns=1.61,  # ~$5.0bn bridge, termed out as high yield
                cash_rate=0.1350,
                sweepable=True,
            ),
            DebtTranche(
                # Sized so total debt + preferred reaches the ~87% of the
                # transaction that was actually reported, which in turn makes the
                # modelled equity cheque land near KKR's real one. An earlier
                # version of this case under-sized the strip and produced a $7.6bn
                # cheque against a reported ~$3.2bn — every return figure struck
                # on it was therefore meaningless.
                name="PIK debentures & exchangeable preferred",
                leverage_turns=2.71,  # ~$8.4bn
                cash_rate=0.0,
                pik_rate=0.1500,
                sweepable=False,
            ),
        ],
        revolver=RevolverAssumptions(commitment=1500.0, cash_rate=0.1150, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.020,  # roughly $1bn of advisory/legal on ~$30bn
        financing_fee_pct_debt=0.020,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=500.0,
        cash_sweep_pct=1.0,
        # The divestitures were agreed at or shortly after close and were the
        # whole reason the structure was thought to work. Without them the model
        # reports a deal that cannot service itself — which is true of the
        # structure alone and false of the plan.
        divestitures=[
            Divestiture(year=1, proceeds=2500.0, label="European Nabisco businesses"),
            Divestiture(year=2, proceeds=2600.0, label="Del Monte"),
        ],
        hold_years=5,
        exit_multiple=9.5,
    ),
    realised=Assumptions(
        entry_ebitda=_RJR_EBITDA,
        entry_multiple=9.71,
        operating=OperatingAssumptions(
            entry_revenue=_RJR_REVENUE,
            # The same divestitures, then Marlboro Friday in year 5.
            revenue_growth=[-0.14, -0.11, 0.03, 0.03, -0.05, 0.02],
            ebitda_margin=[0.190, 0.205, 0.212, 0.210, 0.172, 0.178],
            da_pct_revenue=0.040,
            capex_pct_revenue=0.045,
            nwc_pct_revenue=0.12,
            tax_rate=0.38,
        ),
        tranches=[
            DebtTranche(name="Senior secured bank facilities", leverage_turns=4.68, cash_rate=0.1150,
                        mandatory_amort_pct=0.08, sweepable=True),
            DebtTranche(name="Subordinated / increasing-rate notes", leverage_turns=1.61, cash_rate=0.1350, sweepable=True),
            DebtTranche(name="PIK debentures & exchangeable preferred", leverage_turns=2.71,
                        cash_rate=0.0, pik_rate=0.1500, sweepable=False),
        ],
        revolver=RevolverAssumptions(commitment=1500.0, cash_rate=0.1150, undrawn_fee=0.005),
        transaction_fee_pct_ev=0.020,
        financing_fee_pct_debt=0.020,
        financing_fee_tenor_years=7,
        exit_fee_pct_ev=0.010,
        nol_limit_pct=0.0,
        minimum_cash=500.0,
        cash_sweep_pct=1.0,
        divestitures=[
            Divestiture(year=1, proceeds=2500.0, label="European Nabisco businesses"),
            Divestiture(year=2, proceeds=2600.0, label="Del Monte"),
        ],
        hold_years=6,
        # Tobacco litigation and the price war compressed what anyone would pay.
        exit_multiple=8.0,
    ),
    provenance=[
        Figure("Purchase price", "$109 / share, ~$25bn", "reported",
               "Against a pre-bid price of $56. The board accepted KKR's revised "
               "proposal on 30 November 1988; the buyout closed 28 April 1989.",
               "rjr-wapo"),
        Figure("Total transaction value", "~$30–31bn", "reported",
               "The equity price plus assumed debt and fees. Used as the enterprise "
               "value here.", "barbarians"),
        Figure("Entry EBITDA", "$3,100m", "reported",
               "FY1988, against net sales of $16,956m — an 18.3% margin, which is what "
               "a tobacco-weighted mix looked like before the price wars.", "rjr-wapo"),
        Figure("Entry multiple", "9.7×", "derived",
               "~$30.1bn ÷ $3,100m. Sources quoting 7.5–8.0× are dividing by the $25bn "
               "*equity* price rather than enterprise value — a common and material "
               "error, and worth checking whenever a historic multiple looks low.",
               "rjr-wapo"),
        Figure("Capital structure", "~$21.7bn debt", "reported",
               "Senior bank facilities, a subordinated bridge later termed out into "
               "high yield, and a large PIK / exchangeable-preferred strip. Roughly "
               "87% debt.", "barbarians"),
        Figure("Sponsor equity", "~$3.2bn KKR, ~$3.9bn modelled", "reported",
               "KKR's funds contributed about $3.2bn, of which roughly $1.5bn was "
               "common; co-investors made up the balance of an equity layer that was "
               "roughly 13% of the transaction. The debt and preferred strip here is "
               "sized to that 87% figure, which is what brings the modelled cheque to "
               "$3.9bn — close enough that the returns struck on it mean something.",
               "barbarians"),
        Figure("Interest rates", "11.5% senior / 13.5% sub / 15% PIK", "estimated",
               "Set to 1989 market: prime was around 11% and the high-yield market was "
               "pricing new junk issues in the low-to-mid teens. Rates this high are "
               "the single biggest difference between this deal and every other case "
               "in the library."),
    ],
    model_caveats=[
        "The divestiture proceeds are modelled, but their size and timing are "
        "estimates. Roughly $5.1bn across the first two years is consistent with the Del "
        "Monte and European Nabisco sales; exact figures and dates are not cleanly "
        "public, and this column is sensitive to them — which is itself the point about "
        "a deal underwritten on asset sales.",
        "The engine applies sale proceeds to debt but cannot model the operating "
        "business leaving, so the revenue and margin path carries that by hand. The "
        "paths here represent a tobacco-weighted remainder; they are not fitted to a "
        "reported segment split, because no usable one is public.",
        "The real structure had a substantial exchangeable-preferred layer sitting "
        "between debt and common. The engine has debt tranches and equity, nothing "
        "between, so the preferred is modelled as a PIK debt tranche. That is the right "
        "economic approximation but it makes the sponsor's position look more levered "
        "than it was.",
        "The 1990 recapitalisation — roughly $1.7bn of fresh equity and $2.25bn of new "
        "bank loans, forced by the reset provisions on the PIK paper — is not modelled. "
        "Follow-on equity is a real feature of distressed holds and one the engine "
        "cannot currently express.",
        "1989 pre-TCJA tax law. The 80% NOL limitation is switched off for this case, "
        "and the interest deduction is unlimited — there was no §163(j) cap.",
    ],
    outcome=Outcome(
        exit_route="Divestitures, a 1991 IPO, and a final exit via the 1995 Borden share exchange",
        exit_year=1995,
        holding_years=6.0,
        realised_moic=1.0,
        realised_irr=0.005,
        confidence="widely reported",
        headline="An IRR reported at well under 1% — six years of work for roughly nothing",
        narrative=(
            "About $22bn flowed to banks, bondholders and preferred holders, and close to "
            "$1bn in fees to KKR, its advisers and the loan syndicate. The equity earned "
            "almost nothing. The business was not mismanaged and the strategic thesis "
            "largely played out — the food assets were sold well. What killed the return "
            "was the price: a contested auction pushed the entry multiple past the point "
            "where any operating performance could rescue it, and then Marlboro Friday "
            "and tobacco litigation took the exit multiple down as well. Overpay at "
            "entry and compress at exit, and the value bridge has nowhere left to find a "
            "return."
        ),
    ),
    source_keys=["rjr-wapo", "rjr-10k94", "barbarians"],
    column_notes={
        "underwriting": (
            "The structure does not survive its own underwriting, and that is the "
            "finding rather than a defect. At the reported 87% debt, cash interest plus "
            "PIK accrual runs close to the whole of a $3.1bn EBITDA, and the mandatory "
            "amortisation on the bank facilities cannot be funded from operations at "
            "all. This is historically exact: RJR could not service the "
            "structure as signed, which is why Del Monte and the European Nabisco "
            "businesses had to be sold, and why KKR still had to inject about $1.7bn "
            "of fresh equity in 1990. A deal that only works if the divestitures clear "
            "at the assumed prices, on the assumed timetable, is a different and much "
            "riskier proposition than the IRR alone suggests — and the engine, which "
            "has no divestiture mechanic, says so by refusing to print a schedule."
        ),
        "realised": (
            "Fails for the same reason, earlier and harder once the price war "
            "compresses margin. Note the entry multiple of 9.7×, not the 7.5–8.0× "
            "widely quoted: those figures divide by the $25bn equity price rather than "
            "enterprise value. Two turns of entry multiple is the difference between a "
            "hard deal and an impossible one."
        ),
    },
)


CASES: list[CaseStudy] = [HILTON, HCA, TXU, RJR]

BY_SLUG: dict[str, CaseStudy] = {c.slug: c for c in CASES}

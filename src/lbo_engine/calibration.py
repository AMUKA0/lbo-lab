"""Market-range guardrails: is this assumption plausible, not just computable?

Each check compares an input against a benchmark band compiled from published
market data. Figures are approximate by nature (annual survey data, rounded to
be honest about their precision) and each carries its source. A flag never
blocks a run — you are allowed to model 2007 — it just tells you that you are.

Benchmark vintage: compiled mid-2026 from 2024–2025 survey publications.
Refresh annually; these numbers age slowly but they do age.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lbo_engine.assumptions import Assumptions

Level = Literal["amber", "info"]


@dataclass(frozen=True)
class Flag:
    field: str
    level: Level
    message: str
    source: str


BENCHMARKS = {
    "entry_multiple": {
        "band": (8.0, 12.5),
        "note": "US/EU buyout purchase-price multiples have run ~10–12× EBITDA in recent years",
        "source": "Bain Global Private Equity Report; S&P LCD purchase-price multiple series",
    },
    "total_leverage": {
        "band": (3.5, 6.0),
        "note": "sponsored-deal debt/EBITDA has centred ~4.5–5.5×; >6× marks the 2007/2021 peaks",
        "source": "PitchBook LCD leveraged-loan statistics",
    },
    "senior_rate": {
        "band": (0.05, 0.11),
        "note": "first-lien institutional term loans have priced around base + 300–500bps",
        "source": "PitchBook LCD new-issue spread series",
    },
    "revenue_growth": {
        "band": (-0.02, 0.10),
        "note": "sustained double-digit growth is a top-decile operating case for buyout targets",
        "source": "Bain Global Private Equity Report (value-creation analyses)",
    },
    "hold_years": {
        "band": (4, 7),
        "note": "median buyout hold has been ~5–6 years",
        "source": "Bain Global Private Equity Report (exit analyses)",
    },
}


def check_assumptions(a: Assumptions) -> list[Flag]:
    """Return every guardrail flag the deal trips, in display order."""
    flags: list[Flag] = []

    lo, hi = BENCHMARKS["entry_multiple"]["band"]
    if a.entry_multiple > hi:
        flags.append(Flag(
            "entry_multiple", "amber",
            f"Entry at {a.entry_multiple:.1f}× is above the typical {lo:.0f}–{hi:.1f}× band — "
            "you are underwriting a premium price and every other assumption must work harder.",
            BENCHMARKS["entry_multiple"]["source"],
        ))
    elif a.entry_multiple < lo:
        flags.append(Flag(
            "entry_multiple", "info",
            f"Entry at {a.entry_multiple:.1f}× is below the typical {lo:.0f}–{hi:.1f}× band — "
            "cheap for a reason? Real bargains at auction are rare.",
            BENCHMARKS["entry_multiple"]["source"],
        ))

    # Priced on one EBITDA, run off another. Legitimate — a normalised entry
    # figure is standard — but it moves the effective entry multiple without
    # appearing anywhere, so it is surfaced rather than left to be discovered.
    gap = a.entry_ebitda_gap()
    if gap > 1.15 or gap < 0.87:
        at_entry = a.entry_ebitda / gap
        year_one = at_entry * (1.0 + a.growth_schedule()[0])
        direction = "above" if gap > 1 else "below"
        flags.append(Flag(
            "entry_ebitda", "amber",
            f"Priced on {a.entry_ebitda:,.0f} of EBITDA, {abs(gap - 1) * 100:.0f}% "
            f"{direction} the {at_entry:,.0f} the operating build implies at entry "
            f"({year_one:,.0f} in year one). Normalising is defensible and often "
            f"right — but on the business the model actually projects, the entry "
            f"multiple is {a.entry_multiple * gap:.1f}×, not {a.entry_multiple:.1f}×, "
            "and a reader comparing this deal to another will use the headline.",
            "State the normalisation and show both multiples.",
        ))

    lo, hi = BENCHMARKS["total_leverage"]["band"]
    lev = a.total_leverage_turns
    if lev > hi:
        flags.append(Flag(
            "leverage", "amber",
            f"Total leverage of {lev:.2f}× EBITDA is above the ~{lo:.1f}–{hi:.1f}× sponsored norm — "
            "deals levered here cluster in 2007 and 2021, and how did that go.",
            BENCHMARKS["total_leverage"]["source"],
        ))

    lo, hi = BENCHMARKS["senior_rate"]["band"]
    senior = a.tranches[0]
    if senior.cash_rate < lo:
        flags.append(Flag(
            "senior_rate", "amber",
            f"Senior at {senior.cash_rate:.1%} is below plausible levered-credit pricing "
            f"(~{lo:.0%}–{hi:.0%}) — cheap debt is doing your returns for you.",
            BENCHMARKS["senior_rate"]["source"],
        ))

    lo, hi = BENCHMARKS["revenue_growth"]["band"]
    max_growth = max(a.growth_schedule())
    if max_growth > hi:
        flags.append(Flag(
            "revenue_growth", "amber",
            f"Revenue growth of {max_growth:.0%} is a top-decile operating case — "
            "fine as an upside, dangerous as a base.",
            BENCHMARKS["revenue_growth"]["source"],
        ))

    if a.exit_multiple > a.entry_multiple:
        flags.append(Flag(
            "exit_multiple", "amber",
            f"Exit ({a.exit_multiple:.1f}×) above entry ({a.entry_multiple:.1f}×) assumes multiple "
            "expansion — the driver you control least. Underwrite flat and let expansion be upside.",
            "Standard underwriting discipline; see any IC memo template",
        ))

    margins = a.margin_schedule()
    if margins[-1] - margins[0] > 0.03:
        flags.append(Flag(
            "ebitda_margin", "amber",
            f"Margin expanding {(margins[-1] - margins[0]) * 100:.0f}pts over the hold — "
            ">300bps of expansion is a serious operational-improvement claim; name the initiatives.",
            "Bain Global Private Equity Report (value-creation analyses)",
        ))

    lo, hi = BENCHMARKS["hold_years"]["band"]
    if a.hold_years < lo:
        flags.append(Flag(
            "hold_years", "info",
            f"A {a.hold_years}-year hold is short of the ~5–6 year median — quick flips need "
            "either multiple expansion or a pre-baked exit.",
            BENCHMARKS["hold_years"]["source"],
        ))

    if a.cash_sweep_pct < 0.5:
        flags.append(Flag(
            "cash_sweep", "info",
            f"Sweeping only {a.cash_sweep_pct:.0%} of excess cash — credit agreements typically "
            "require 50–100% ECF sweeps at these leverage levels.",
            "Standard leveraged credit agreement terms",
        ))

    return flags

"""What this model does not do, stated where a reader meets it.

The README has always carried a "genuine gaps" list, and a README is the wrong
place for it: the person most likely to be misled is the one moving sliders in
the simulator, who has not read it. So the list lives here, is served over the
API, and is rendered on the page where the numbers are.

One source of truth, not two. A copy in the client would rot the first time a
gap got closed — which has now happened four times (§163(j), covenants, the
maturity wall, interest on cash), and each time the prose would have gone on
claiming a limitation the engine no longer had. `tests/test_limitations.py`
guards the direction that matters: nothing here may name a mechanic the engine
has actually got.

Each entry says what is missing AND what it would change, because "no §382
limitation" tells a reader nothing on its own. A limitation without its
consequence is a disclaimer; with its consequence it is a caveat someone can
act on.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Limitation:
    """One thing the model does not do, and the direction it errs in."""

    title: str
    detail: str
    # "overstates" / "understates" / "neutral" — which way the omission pushes
    # the reported return. A reader deciding how much to trust a number wants
    # the sign more than the magnitude.
    direction: str


# Ordered by how likely each is to matter on a normal base case, not by how
# interesting it is to explain.
LIMITATIONS: list[Limitation] = [
    Limitation(
        title="No management rollover, option pool or transaction bonuses",
        detail=(
            "Management equity dilutes sponsor proceeds at exit, typically by a "
            "low-single-digit percentage of equity value, and the option pool "
            "usually strikes at entry so it participates in the whole gain. Every "
            "IRR here is struck on undiluted sponsor equity."
        ),
        direction="overstates",
    ),
    Limitation(
        title="No add-on acquisitions",
        detail=(
            "Buy-and-build is a major value-creation lever and the model cannot "
            "express it: there is one company, and it grows organically or not at "
            "all. A platform strategy bought at 12× and bolting on at 7× creates "
            "value this model has no line for."
        ),
        direction="understates",
    ),
    Limitation(
        title="Annual periods and fixed rates",
        detail=(
            "Real facilities pay quarterly on a floating base plus a margin, and "
            "a company can breach a covenant in Q2 and be back inside by Q4. "
            "Annual periodicity smooths that away, and fixed rates mean a rate "
            "path is a manual re-run rather than an input. Both are the right "
            "screening conventions and both cost precision."
        ),
        direction="neutral",
    ),
    Limitation(
        title="No §382 limitation on acquired losses",
        detail=(
            "An LBO *is* an ownership change, so a target's pre-existing net "
            "operating losses would be capped at roughly equity value × the "
            "long-term tax-exempt rate. Losses generated after close — which is "
            "what the model actually produces — are unaffected, so this bites "
            "only on a deal buying a company that already had carryforwards."
        ),
        direction="overstates",
    ),
    Limitation(
        title="A flat cash sweep, not a leverage grid",
        detail=(
            "Credit agreements step the sweep down as leverage falls — 75% above "
            "5.0×, 50% between 4.0× and 5.0×, nil below. A flat percentage "
            "repays too much late in a deleveraging deal and too little early."
        ),
        direction="neutral",
    ),
    Limitation(
        title="One company, one revenue line",
        detail=(
            "No segment build, so a divestiture's operating effect has to be "
            "entered by hand as a change to the revenue and margin path. The "
            "model cannot work out what leaves with a business it never knew "
            "about separately."
        ),
        direction="neutral",
    ),
    Limitation(
        title="No unamortised-fee write-off on early repayment",
        detail=(
            "Repaying a facility early writes off the remaining capitalised "
            "financing fee. It is a non-cash P&L item that never touches returns, "
            "which is why it is absent — but a reader reconciling to audited "
            "accounts will find it missing."
        ),
        direction="neutral",
    ),
    Limitation(
        title="Exit equity is floored at zero",
        detail=(
            "Limited liability, so a wipeout reports as a wipeout rather than as "
            "negative equity. The consequence is that the value bridge reconciles "
            "exactly only for solvent exits."
        ),
        direction="neutral",
    ),
]


def limitations_payload() -> list[dict]:
    return [asdict(limit) for limit in LIMITATIONS]

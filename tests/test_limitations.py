"""The stated limits must not outlive the code.

Four gaps have been closed since the list was first written — §163(j),
covenants, the maturity wall, interest on cash — and each time the prose would
have gone on claiming a limitation the engine no longer had. That failure mode
has already bitten this project twice in the case-study caveats, which is why
those have their own staleness guard.

This is the same guard for the simulator's list. It is deliberately one-sided:
a limitation that is genuinely missing is fine to leave off, but a limitation
the engine has since implemented is a lie on a live page.
"""

import pytest

from api.limitations import LIMITATIONS, limitations_payload
from lbo_engine import Assumptions


# Phrases that would be false now, mapped to the field or type that makes them
# false. Grown by hand as gaps get closed, which is the point: closing a gap
# should require deleting its entry from the list, and this fails loudly if the
# deletion is forgotten.
IMPLEMENTED = {
    "163(j)": "interest_limitation",
    "interest limitation": "interest_limitation",
    "covenant test": "covenants",
    "maintenance covenant": "covenants",
    "maturity wall": "tranches",
    "interest income": "cash_deposit_rate",
    "interest on cash": "cash_deposit_rate",
    "dividend recap": "recaps",
    "divestiture": "divestitures",
    "pik toggle": "tranches",
}


@pytest.mark.parametrize("limitation", LIMITATIONS, ids=lambda x: x.title[:40])
def test_no_limitation_claims_something_the_engine_has(limitation):
    fields = set(Assumptions.model_fields)
    prose = f"{limitation.title} {limitation.detail}".lower()

    for phrase, field in IMPLEMENTED.items():
        if phrase not in prose or field not in fields:
            continue
        # A mention is allowed; a DENIAL is not. "No covenant test" is the shape
        # that rots, not "the covenant test is annual".
        #
        # The window is two words, and it has to be: at forty characters this
        # flagged "no segment build, so a divestiture's operating effect" —
        # where the denial attaches to the segment build and the divestiture
        # mechanic is being described, not denied. A guard that cries wolf on
        # true prose gets switched off, which is worse than not having it.
        before = prose[:prose.find(phrase)].split()[-2:]
        denials = {"no", "not", "cannot", "without", "absent", "missing", "lacks"}
        assert not (denials & set(before)), (
            f"{limitation.title!r} denies {phrase!r}, which the engine "
            f"implements via `{field}`. Delete the entry rather than leaving a "
            "live page claiming a gap that was closed."
        )


def test_the_guard_actually_fires():
    """A staleness guard that cannot fail is decoration. This is the exact entry
    that sat in the README until §163(j) was built, and it must be rejected."""
    from api.limitations import Limitation

    stale = Limitation(
        title="No §163(j) interest limitation",
        detail=(
            "The 30%-of-adjusted-taxable-income cap is the tax provision that "
            "binds hardest on a modern US LBO, and it is absent while the easier "
            "§172(a) NOL rule is implemented. On a six-turn structure this "
            "understates cash tax."
        ),
        direction="overstates",
    )
    with pytest.raises(AssertionError, match="interest_limitation"):
        test_no_limitation_claims_something_the_engine_has(stale)


def test_every_limitation_says_which_way_it_errs():
    """The sign matters more than the magnitude. A reader deciding how much to
    trust a number wants to know whether the omission flatters it."""
    for limitation in LIMITATIONS:
        assert limitation.direction in {"overstates", "understates", "neutral"}, (
            f"{limitation.title}: {limitation.direction!r}"
        )


def test_every_limitation_says_what_it_would_change():
    """A limitation without its consequence is a disclaimer. With it, it is a
    caveat someone can act on."""
    for limitation in LIMITATIONS:
        assert len(limitation.detail) > 120, (
            f"{limitation.title}: too thin to be useful — say what it changes"
        )


def test_the_payload_survives_serialisation():
    payload = limitations_payload()
    assert len(payload) == len(LIMITATIONS)
    assert all({"title", "detail", "direction"} == set(p) for p in payload)

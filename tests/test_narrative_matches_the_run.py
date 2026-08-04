"""Prose on a case page must not contradict the numbers beside it.

This is the failure mode the whole case-study design claims to prevent, and it
happened twice anyway. TXU's break note said the engine saw a "$977m gap" while
the engine's own message on the same page said $1,923.8m. Dollar General's
column note said the exit was "underwritten BELOW entry at 9.0x" when the
assumption had been changed to 9.75× — flat — with the code comment updated and
the prose forgotten.

Both were written by hand, both drifted when a number moved, and neither was
caught because nothing compared them. Two guards now:

1. Engine figures are PLACEHOLDERS filled from the run, so they cannot be typed
   wrong. `test_no_engine_figure_is_hardcoded` keeps them that way.
2. Multiples quoted in prose must be assumptions the column actually holds.
"""

import re

import pytest

from api.case_studies import CASES
from api.main import _replay, _shortfall_from, case_detail


def _columns():
    for case in CASES:
        for name in ("underwriting", "realised"):
            if getattr(case, name) is not None:
                yield pytest.param(case, name, id=f"{case.slug}-{name}")


COLUMNS = list(_columns())

# "9.75x", "9.75×", "14.9x" — a multiple being asserted in prose.
MULTIPLE = re.compile(r"(\d+\.?\d*)\s*[x×](?![a-z])", re.IGNORECASE)
# "$1,924m", "$26.0bn" — a money figure being asserted in prose.
MONEY = re.compile(r"\$([\d,]+\.?\d*)\s*(m|bn)\b", re.IGNORECASE)


# Language that CLAIMS a multiple is an assumption rather than an outcome. A
# note is free to say "returns 3.1x" — that is an output. It is not free to say
# "underwritten at 9.0x" when the input reads 9.75.
ASSERTS_AN_ASSUMPTION = (
    "underwritten at", "underwritten flat", "underwritten below",
    "underwritten above", "entry at", "exit at", "held at", "held flat",
    "priced at", "bought at", "entry multiple of", "exit multiple of",
)


@pytest.mark.parametrize("case,column", COLUMNS)
def test_any_multiple_a_note_claims_as_an_ASSUMPTION_really_is_one(case, column):
    """Scoped to sentences that assert an assumption, not every number.

    Dollar General claimed the exit was "underwritten BELOW entry at 9.0x"
    against an actual 9.75× — flat — which moved the reported IRR by three
    points. A note may quote what the model RETURNED without restriction; what
    it may not do is describe an input the model does not hold.
    """
    note = case.column_notes.get(column)
    if not note:
        pytest.skip("no column note")

    deal = getattr(case, column)
    legitimate = {round(deal.entry_multiple, 2), round(deal.exit_multiple, 2),
                  round(deal.total_leverage_turns, 2)}
    legitimate |= {round(t.leverage_turns, 2) for t in deal.tranches}
    # Notes legitimately compare the two columns, so the other one's inputs count.
    for other in ("underwriting", "realised"):
        alt = getattr(case, other)
        if alt is not None:
            legitimate |= {round(alt.entry_multiple, 2), round(alt.exit_multiple, 2)}

    for sentence in re.split(r"(?<=[.]) ", note):
        lowered = sentence.lower()
        if not any(phrase in lowered for phrase in ASSERTS_AN_ASSUMPTION):
            continue
        for raw in MULTIPLE.findall(sentence):
            # Compared at the precision the PROSE chose. RJR's note says "9.7×"
            # where the input reads 9.71, and rounding for readability is not
            # drift — the failure this guards against is 9.0 against 9.75, which
            # survives rounding at any precision.
            places = len(raw.split(".")[1]) if "." in raw else 0
            quoted = float(raw)
            assert any(round(v, places) == quoted for v in legitimate), (
                f"{case.slug}/{column}: this sentence asserts {raw}x as an "
                f"assumption, but the column holds {sorted(legitimate)} — "
                f"{sentence.strip()}"
            )


@pytest.mark.parametrize("case,column", COLUMNS)
def test_no_engine_figure_is_hardcoded_in_a_break_note(case, column):
    """The shortfall must be a placeholder, never a typed number.

    Checked by construction rather than by comparison: if the note carries a
    money figure in the sentence describing the gap, that figure was typed, and
    a typed figure goes stale the moment an assumption moves.
    """
    note = next((b for b in case.break_notes if b.column == column), None)
    if note is None:
        pytest.skip("this column does not break")

    saw = note.what_the_engine_saw
    for sentence in re.split(r"(?<=[.])\s+", saw):
        mentions_gap = any(
            word in sentence.lower() for word in ("gap", "shortfall", "could not fund")
        )
        if mentions_gap and "{shortfall}" not in sentence:
            assert not MONEY.search(sentence), (
                f"{case.slug}/{column}: the sentence describing the gap carries a "
                f"typed figure — use {{shortfall}} so the run fills it.\n  {sentence}"
            )


@pytest.mark.parametrize("case,column", COLUMNS)
def test_the_filled_note_agrees_with_the_engine_message(case, column):
    """End to end: whatever the note ends up saying about the gap has to be the
    number the engine reported for that column."""
    replay = _replay(getattr(case, column))
    note = next((b for b in case.break_notes if b.column == column), None)
    if note is None or not replay["failed"]:
        pytest.skip("this column does not break")

    shortfall = _shortfall_from(replay["message"])
    if shortfall is None:
        pytest.skip("this failure carries no shortfall (covenant or maturity)")

    if "{shortfall}" not in note.what_the_engine_saw:
        pytest.skip("this note does not quote the gap")

    detail = case_detail(case.slug)[column]["break_note"]
    prose = " ".join(v for v in detail.values() if isinstance(v, str))
    assert f"${shortfall:,.0f}m" in prose, (
        f"{case.slug}/{column}: engine reported {shortfall:,.1f} but the filled "
        f"note does not carry it"
    )


@pytest.mark.parametrize("case,column", COLUMNS)
def test_break_notes_only_exist_where_the_column_breaks(case, column):
    """And every break has one. A note describing a failure that no longer
    happens is the same class of error running the other way."""
    breaks = _replay(getattr(case, column))["failed"]
    has_note = any(b.column == column for b in case.break_notes)
    assert breaks == has_note, (
        f"{case.slug}/{column}: breaks={breaks} but break_note={has_note}"
    )


def test_the_shortfall_parser_is_pinned_to_the_message_wording():
    """`_shortfall_from` reads a string the engine produced. That is fragile by
    nature, so the coupling is asserted rather than hoped for: change the
    failure message and this fails immediately, rather than the case pages
    quietly losing their numbers."""
    from lbo_engine.failures import LiquidityFailure

    message = str(LiquidityFailure(4, 1234.5, 100.0))
    assert _shortfall_from(message) == pytest.approx(1234.5)
    assert _shortfall_from(None) is None
    assert _shortfall_from("no numbers here") is None


class TestTheGuardsActuallyFire:
    """Both bugs, reconstructed. A staleness guard that cannot fail is
    decoration, and these are the exact strings that shipped."""

    def test_it_catches_the_dollar_general_multiple(self):
        from api.case_studies import DOLLAR_GENERAL

        stale = DOLLAR_GENERAL.column_notes["underwriting"].replace(
            "underwritten flat to entry at 9.75×",
            "underwritten BELOW entry at 9.0x",
        )
        broken = type(DOLLAR_GENERAL)(
            **{**DOLLAR_GENERAL.__dict__,
               "column_notes": {**DOLLAR_GENERAL.column_notes, "underwriting": stale}}
        )
        with pytest.raises(AssertionError, match="asserts 9.0x as an assumption"):
            test_any_multiple_a_note_claims_as_an_ASSUMPTION_really_is_one(
                broken, "underwriting")

    def test_it_catches_the_txu_shortfall(self):
        from api.case_studies import TXU, BreakNote

        note = next(b for b in TXU.break_notes if b.column == "realised")
        stale = BreakNote(
            column=note.column, year=note.year, calendar=note.calendar,
            headline=note.headline, what_happened=note.what_happened,
            what_the_engine_saw=note.what_the_engine_saw.replace(
                "a {shortfall} gap", "a $977m gap"),
            what_the_engine_cannot_see=note.what_the_engine_cannot_see,
        )
        broken = type(TXU)(**{**TXU.__dict__, "break_notes": [stale]})
        with pytest.raises(AssertionError, match="use .shortfall. so the run fills it"):
            test_no_engine_figure_is_hardcoded_in_a_break_note(broken, "realised")

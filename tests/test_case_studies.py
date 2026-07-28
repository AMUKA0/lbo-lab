"""Case-study library tests.

Two kinds of assertion here. The first is ordinary transport checking: the
endpoints respond, the payload is strict JSON, an unknown slug is a 404.

The second is more interesting and is the reason this file exists separately.
The library's entire claim is that the underwriting assumptions contain no
hindsight, and that claim is only worth anything if something enforces it. The
tests below encode the two ways hindsight actually leaks into a retrospective
case study — assuming multiple expansion you only know happened, and citing a
source that does not exist — and fail if either appears.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.case_studies import CASES, SOURCES, BY_SLUG
from api.main import app

client = TestClient(app)

SLUGS = [c.slug for c in CASES]


def test_index_lists_the_library():
    body = client.get("/api/cases").json()
    assert [c["slug"] for c in body["cases"]] == SLUGS
    # The index must be cheap: it carries no modelled run, only the card facts.
    assert "underwriting" not in body["cases"][0]


def test_unknown_slug_is_a_404():
    assert client.get("/api/cases/enron-1999").status_code == 404


@pytest.mark.parametrize("slug", SLUGS)
def test_every_case_replays(slug):
    response = client.get(f"/api/cases/{slug}")
    assert response.status_code == 200

    raw = response.text
    assert "NaN" not in raw and "Infinity" not in raw
    body = json.loads(raw)

    assert body["underwriting"] is not None
    for column in ("underwriting", "realised"):
        col = body[column]
        if col is None:
            continue
        # A failed column is a legitimate result — three of the eight runs in
        # this library are supposed to fail — but it must say why.
        if col["failed"]:
            assert col["message"]
            assert col["run"] is None
        else:
            assert col["run"] is not None
            assert len(col["run"]["years"]) == col["assumptions"]["hold_years"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_underwriting_never_assumes_multiple_expansion(case):
    """The commonest way hindsight smuggles itself into a retrospective case:
    underwriting an exit multiple above entry because you happen to know the
    market re-rated. A sponsor case that needs expansion to work is a different
    proposition and would not have cleared a committee at these entry prices."""
    a = case.underwriting
    assert a.exit_multiple <= a.entry_multiple, (
        f"{case.slug} underwrites {a.exit_multiple}× out of {a.entry_multiple}× in"
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_the_realised_column_shares_the_structure(case):
    """Only the operating path, the exit and any recaps may differ between the
    two columns. If the capital *structure* moved as well, the comparison would
    be measuring two things at once and the 'model fed reality' claim would be
    empty. Recaps are exempt because a recap is an event that happened, not an
    underwriting assumption — HCA's 2010 dividend belongs in the realised column
    and nowhere near the one built from pre-close information."""
    if case.realised is None:
        return
    u, r = case.underwriting, case.realised

    assert u.entry_ebitda == r.entry_ebitda
    assert u.entry_multiple == r.entry_multiple
    assert [(t.name, t.leverage_turns, t.cash_rate, t.pik_rate) for t in u.tranches] == [
        (t.name, t.leverage_turns, t.cash_rate, t.pik_rate) for t in r.tranches
    ]
    assert u.revolver.commitment == r.revolver.commitment
    assert u.transaction_fee_pct_ev == r.transaction_fee_pct_ev
    assert u.financing_fee_pct_debt == r.financing_fee_pct_debt


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_every_cited_source_resolves(case):
    """A provenance badge pointing at a source key that does not exist is worse
    than no badge, because it looks like a citation."""
    keys = {s.key for s in SOURCES}
    for figure in case.provenance:
        if figure.source is not None:
            assert figure.source in keys, f"{case.slug}: dangling source {figure.source!r}"
    for key in case.source_keys:
        assert key in keys


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_every_case_states_its_limits(case):
    """No deal in this library fits the engine perfectly. A case with no caveats
    would mean someone stopped looking."""
    assert case.model_caveats
    assert case.could_not_have_known
    assert case.outcome.narrative


def test_provenance_is_labelled_with_a_known_basis():
    allowed = {"reported", "derived", "estimated"}
    for case in CASES:
        for figure in case.provenance:
            assert figure.basis in allowed
            # An estimate without reasoning is a guess wearing a badge.
            assert len(figure.note) > 40


def test_the_library_spans_the_range_of_outcomes():
    """A case library of four winners teaches nothing. This asserts the shape of
    the set, so a later edit can't quietly turn it into a highlight reel."""
    verdicts = {c.verdict for c in CASES}
    assert "wipeout" in verdicts
    assert "home run" in verdicts
    assert len(verdicts) >= 3


def test_hilton_needs_its_restructuring_and_reproduces_the_outcome_with_it():
    """The library's most load-bearing result, pinned in both halves.

    Strip the 2010 restructuring out and the structure runs out of liquidity in
    year three — the model locating the crisis from the numbers alone, in the
    exact year Blackstone renegotiated. Put it back, as reported, and the deal
    runs the full eleven years and lands on the reported multiple. Either half
    alone is a much weaker claim than the pair.
    """
    from lbo_engine import Assumptions, run_lbo

    case = BY_SLUG["hilton-blackstone-2007"]
    assert case.realised.injections, "the restructuring is what this test is about"

    without = case.realised.model_dump()
    without["injections"] = []
    with pytest.raises(ValueError, match="revolver"):
        run_lbo(Assumptions.model_validate(without))

    body = client.get("/api/cases/hilton-blackstone-2007").json()
    realised = body["realised"]
    assert not realised["failed"]
    # Reported ~3.0x. Anything inside a fifth of a turn is reproducing it.
    assert abs(realised["moic"] - body["outcome"]["realised_moic"]) < 0.2
    # And the deal is underwritable as signed — the failure came from what
    # happened, not from the price.
    assert body["underwriting"]["failed"] is False



def test_txu_underwrites_respectably_and_still_lost_everything():
    """TXU is in the library because the model *likes* it. If a future edit made
    the underwriting column fail, the case would lose its entire argument."""
    body = client.get("/api/cases/txu-kkr-tpg-2007").json()
    assert body["underwriting"]["failed"] is False
    assert body["underwriting"]["irr"] > 0.05
    assert body["outcome"]["realised_moic"] == 0.0
    assert BY_SLUG["txu-kkr-tpg-2007"].verdict == "wipeout"


@pytest.mark.parametrize("slug", SLUGS)
def test_every_break_is_explained(slug):
    """A liquidity break with no account of the year is a dead end. If a column
    breaks, it must say what happened, what the engine computed, and what the
    engine could not see — and the third is the one that stops the other two
    being read as a claim the model got it right."""
    body = client.get(f"/api/cases/{slug}").json()
    for column in ("underwriting", "realised"):
        col = body[column]
        if col is None or not col["failed"]:
            continue
        note = col["break_note"]
        assert note is not None, f"{slug}/{column} breaks with no explanation"
        assert note["year"] == col["breaks_in_year"], (
            f"{slug}/{column}: note describes year {note['year']} but the engine "
            f"breaks in year {col['breaks_in_year']}"
        )
        for field in ("what_happened", "what_the_engine_saw", "what_the_engine_cannot_see"):
            assert len(note[field]) > 120, f"{slug}/{column}: {field} is too thin to be useful"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_no_break_note_without_a_break(case):
    """The inverse: an explanation for a break that no longer happens is stale
    documentation, and worse than none, because it describes a run the reader
    cannot see."""
    from lbo_engine import run_lbo

    for note in case.break_notes:
        assumptions = getattr(case, note.column)
        assert assumptions is not None
        with pytest.raises(ValueError):
            run_lbo(assumptions)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_column_notes_do_not_describe_a_run_that_no_longer_happens(case):
    """Prose rots faster than code. A column note claiming the structure "does
    not survive" or that the engine is "refusing to print" must not sit above a
    column that runs — that exact contradiction shipped once, because the note
    was written when RJR had no divestiture mechanic and was never revisited
    when it got one."""
    from lbo_engine import run_lbo

    FAILURE_LANGUAGE = (
        "does not survive",
        "refusing to print",
        "cannot service itself",
        "fails for the same reason",
    )
    for column, note in case.column_notes.items():
        assumptions = getattr(case, column)
        if assumptions is None:
            continue
        try:
            run_lbo(assumptions)
        except ValueError:
            continue  # the column does break; failure language is fair
        lowered = note.lower()
        for phrase in FAILURE_LANGUAGE:
            assert phrase not in lowered, (
                f"{case.slug}/{column} runs to exit, but its note says {phrase!r}"
            )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_reported_moic_and_irr_are_mutually_consistent(case):
    """A reported pair has to be arithmetically possible. Held at a single
    terminal exit, MOIC^(1/years)-1 is the floor for IRR; anything above it
    requires capital to have come back early, which is a real and common thing
    — but a *large* excess means the pair was copied from somewhere without
    being checked. Hilton at 3.0x/11y was published here as 15% when the
    compounded floor is 10.5%."""
    o = case.outcome
    if o.realised_moic is None or o.realised_irr is None or o.realised_moic <= 0:
        return
    floor = o.realised_moic ** (1.0 / o.holding_years) - 1.0
    assert o.realised_irr >= floor - 1e-9, (
        f"{case.slug}: {o.realised_moic}x over {o.holding_years}y compounds to "
        f"{floor:.1%}, but {o.realised_irr:.1%} is reported — below the floor is impossible"
    )
    # Early distributions can lift IRR a long way, but not without limit.
    assert o.realised_irr <= floor + 0.10, (
        f"{case.slug}: {o.realised_irr:.1%} sits more than 10pts above the "
        f"{floor:.1%} compounded floor; state the distribution profile or lower it"
    )

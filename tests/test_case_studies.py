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

    # Operating cash items too. These were unchecked, and the gap was real:
    # Hilton's realised column quietly carried 150bp less capex, which is what
    # kept it alive to year eleven instead of breaking in year two. They may
    # still differ — a company genuinely does cut capex in a downturn — but the
    # difference has to be surfaced on the page, not discovered by a reviewer.
    from api.main import _column_deltas

    disclosed = {d["field"] for d in _column_deltas(case)}
    for label, a, b in (
        ("Capex (% of revenue)", u.operating.capex_pct_revenue, r.operating.capex_pct_revenue),
        ("D&A (% of revenue)", u.operating.da_pct_revenue, r.operating.da_pct_revenue),
        ("Working capital (% of revenue)", u.operating.nwc_pct_revenue, r.operating.nwc_pct_revenue),
        ("Cash sweep", u.cash_sweep_pct, r.cash_sweep_pct),
        ("Minimum cash", u.minimum_cash, r.minimum_cash),
    ):
        if a != b:
            assert label in disclosed, f"{case.slug}: {label} differs but is not disclosed"


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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_underwriting_never_assumes_it_will_need_rescuing(case):
    """Rescue capital in an underwriting column is hindsight by definition.

    Nobody signs a deal on the basis that the sponsor will have to inject
    equity in year two — if you knew that, you would not sign it. Follow-on
    capital belongs in the realised column, describing what actually had to
    happen, and nowhere near the case built from pre-close information.

    This exists because it happened: RJR's 1990 recapitalisation was written
    into the underwriting column by mistake, and it moved that column from
    0.81x to 1.02x — flattering it into near-exact agreement with the reported
    outcome, which is precisely how a retrospective case study fools its author.
    """
    assert not case.underwriting.injections, (
        f"{case.slug} underwrites {len(case.underwriting.injections)} rescue "
        "injection(s) — that is hindsight, not a plan"
    )


BRIDGE_ROWS = (
    "ebitda_growth",
    "multiple_expansion",
    "deleveraging",
    "divestitures",
    "recapitalisation",
    "follow_on_equity",
    "fee_drag",
)


@pytest.mark.parametrize("slug", SLUGS)
def test_the_rows_the_client_displays_sum_to_the_stated_gain(slug):
    """The engine-level identity test passes whether or not the client renders
    every component, and that gap shipped: `follow_on_equity` was missing from
    both the bridge table and the waterfall, so Hilton's realised column showed
    rows summing to $15,398m under a stated gain of $14,598m — with "0.00 —
    exact" printed underneath.

    This asserts over exactly the field set the client iterates. Adding a
    component to the bridge without adding it to the display now fails here.
    """
    body = client.get(f"/api/cases/{slug}").json()
    for column in ("underwriting", "realised"):
        col = body[column]
        run = col and (col.get("run") or col.get("partial_run"))
        if not run or run["bridge"] is None:
            continue  # a truncated run has no exit and so no bridge
        b = run["bridge"]
        assert sum(b[k] for k in BRIDGE_ROWS) == pytest.approx(b["equity_gain"], abs=1e-6), (
            f"{slug}/{column}: displayed rows do not sum to the stated gain"
        )


def test_every_bridge_component_is_in_the_displayed_row_set():
    """Guards the guard: if a new term is added to BridgeOut, it must be added
    to BRIDGE_ROWS above (and therefore considered for the client) rather than
    silently omitted from both."""
    from api.serialisation import BridgeOut

    computed = {"total_value_created", "equity_gain", "reconciliation_error",
                "entry_equity", "exit_equity", "dividends", "total_invested",
                "total_proceeds"}
    components = set(BridgeOut.model_fields) - computed
    assert components == set(BRIDGE_ROWS), (
        f"bridge components not in the displayed set: {components - set(BRIDGE_ROWS)}"
    )


STALE_CLAIMS = (
    "is not modelled",
    "cannot currently express",
    "the engine has no",
    "no divestiture mechanic",
    "no recap mechanic",
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.slug)
def test_caveats_do_not_deny_mechanics_the_engine_now_has(case):
    """Caveats rot as the engine grows. RJR carried "the 1990 recapitalisation
    is not modelled" for as long as it took to build the injection mechanic and
    then use it on that exact case — in two places, a `model_caveat` and a
    `break_note`, neither of which the existing staleness guard covered.

    This checks the denial phrases against the mechanics actually in use.
    """
    a = case.realised or case.underwriting
    in_use = {
        "injections": bool(a.injections),
        "divestitures": bool(a.divestitures),
        "recaps": bool(a.recaps),
    }
    prose = " ".join(case.model_caveats)
    for note in case.break_notes:
        prose += " " + note.what_the_engine_cannot_see + " " + note.what_the_engine_saw
    lowered = prose.lower()

    for phrase in STALE_CLAIMS:
        if phrase not in lowered:
            continue
        window = lowered[max(0, lowered.index(phrase) - 200):lowered.index(phrase) + 200]
        for mechanic, used in in_use.items():
            hint = {"injections": "recapitalisation", "divestitures": "divestiture",
                    "recaps": "dividend recap"}[mechanic]
            assert not (used and hint in window), (
                f"{case.slug}: {phrase!r} sits beside {hint!r}, which this case uses"
            )

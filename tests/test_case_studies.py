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
    """Only the operating path and the exit may differ between the two columns.
    If the capital structure moved as well, the comparison would be measuring two
    things at once and the 'model fed reality' claim would be empty."""
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


def test_hilton_realised_path_identifies_the_restructuring():
    """The single most load-bearing result in the library, pinned so it can't
    silently change: fed the actual downturn, Hilton's structure as signed runs
    out of liquidity — which is what forced the 2010 debt renegotiation."""
    body = client.get("/api/cases/hilton-blackstone-2007").json()
    realised = body["realised"]
    assert realised["failed"]
    assert "revolver" in realised["message"].lower()
    # And the deal is still underwritable on the numbers as signed — the whole
    # point being that the failure comes from what happened, not from the price.
    assert body["underwriting"]["failed"] is False


def test_txu_underwrites_respectably_and_still_lost_everything():
    """TXU is in the library because the model *likes* it. If a future edit made
    the underwriting column fail, the case would lose its entire argument."""
    body = client.get("/api/cases/txu-kkr-tpg-2007").json()
    assert body["underwriting"]["failed"] is False
    assert body["underwriting"]["irr"] > 0.05
    assert body["outcome"]["realised_moic"] == 0.0
    assert BY_SLUG["txu-kkr-tpg-2007"].verdict == "wipeout"

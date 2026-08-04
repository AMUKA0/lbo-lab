"""Nothing differs between two case columns without the reader being told.

"Same capital structure, fed the operating path that actually happened" is the
central claim of every case page. It is worth nothing unless the reader can see
everything ELSE that moved.

This has now failed twice. First Hilton, whose realised column carried 150bp
less capex — the difference between a deal that runs eleven years and one that
breaks in year two. The fix was a hand-written table of seven fields, plus a
constant called `_MAY_DIFFER` whose comment read "the test suite rejects it".

There was no such test. `_MAY_DIFFER` was referenced nowhere in the repo, and
four more fields were differing silently — `cash_deposit_rate` in all five
cases, and the refinancing assumption on TXU's $24.5bn term loan, which is the
load-bearing judgement in that case. A comment claiming an enforcement that does
not exist is worse than no claim at all, because it stops anyone looking.

So: the table is now derived from `model_dump()`, and this is the test.
"""

import pytest

from api.case_studies import CASES
from api.main import _MAY_DIFFER, _TRANCHE_MAY_DIFFER, _column_deltas, _flatten

WITH_BOTH = [pytest.param(c, id=c.slug) for c in CASES if c.realised is not None]


@pytest.mark.parametrize("case", WITH_BOTH)
def test_nothing_differs_outside_the_permitted_set(case):
    """The claim `_MAY_DIFFER` makes, actually enforced.

    A field differing outside this set is drift rather than news, and would mean
    a case page comparing two things it describes as identical.
    """
    left, right = _flatten(case.underwriting), _flatten(case.realised)

    for field in sorted(set(left) | set(right)):
        if left.get(field) == right.get(field):
            continue
        root = field.split(".")[0].split("[")[0]
        if root == "tranche":
            attribute = field.split(".", 1)[1]
            assert attribute in _TRANCHE_MAY_DIFFER, (
                f"{case.slug}: {field} differs between columns. Tranche PRICING "
                "and SIZE may not move — the pages claim 'the same tranches at "
                "the same rates' in prose, so it has to be true."
            )
            continue
        assert root in _MAY_DIFFER, (
            f"{case.slug}: {field} differs between the columns and is not in "
            "_MAY_DIFFER. Either it is news (add it, and make sure the delta "
            "table renders it) or it is drift (remove the difference)."
        )


@pytest.mark.parametrize("case", WITH_BOTH)
def test_every_difference_reaches_the_reader(case):
    """The guard that actually matters. Whatever differs must appear in the
    table the page renders — not merely be permitted to differ."""
    left, right = _flatten(case.underwriting), _flatten(case.realised)
    differing = {f for f in set(left) | set(right) if left.get(f) != right.get(f)}
    shown = len(_column_deltas(case))
    assert shown == len(differing), (
        f"{case.slug}: {len(differing)} fields differ but the table shows "
        f"{shown}. The table is derived, so this should be impossible — if it "
        "fires, something started filtering again."
    )


@pytest.mark.parametrize("case", WITH_BOTH)
def test_the_deposit_rate_is_disclosed(case):
    """Named specifically because it is the one that hid in all five cases.

    It is legitimate news — a 2007 underwriting assumed ~4.4% on deposits and
    ZIRP delivered near zero — but it was invisible, and on RJR it is worth a
    whole year of survival."""
    if case.underwriting.cash_deposit_rate == case.realised.cash_deposit_rate:
        pytest.skip("this case assumes the same rate in both columns")
    fields = {row["field"] for row in _column_deltas(case)}
    assert "Deposit rate on cash" in fields, case.slug


def test_txu_discloses_the_refinancing_assumption():
    """The specific finding: TXU's realised column flips `refinance_at_maturity`
    to False on the $24.5bn term loan, which is the page's entire thesis about
    how that deal died — and it appeared nowhere.

    It is currently inert, because the deal breaks on liquidity two years before
    the wall. That makes disclosing it MORE important, not less: a reader has no
    other way to learn the switch is there or that it is doing nothing.
    """
    txu = next(c for c in CASES if c.slug.startswith("txu"))
    rows = {row["field"]: (row["underwriting"], row["realised"])
            for row in _column_deltas(txu)}
    matching = [k for k in rows if "refinance at maturity" in k]
    assert matching, f"TXU's refinancing flip is not disclosed. Shown: {list(rows)}"
    assert rows[matching[0]] == ("yes", "no")
    # And it names the tranche rather than saying "tranche[0]".
    assert "term loan" in matching[0].lower(), matching[0]


@pytest.mark.parametrize("case", WITH_BOTH)
def test_the_table_is_legible(case):
    """Every row has a human label and two formatted values. A derived table is
    only an improvement on a hand-written one if it stays readable."""
    for row in _column_deltas(case):
        assert row["field"][0].isupper(), row["field"]
        assert "_" not in row["field"], f"{case.slug}: raw field name — {row['field']}"
        for side in ("underwriting", "realised"):
            assert row[side], f"{case.slug}: empty {side} value for {row['field']}"
            # Bare floats mean a rate slipped through unformatted, which is how
            # "0.06" ended up next to "8.0% → 4.1%" in the first derived version.
            assert not row[side].replace(".", "").replace("-", "").isdigit(), (
                f"{case.slug}: {row['field']} renders as a bare number "
                f"({row[side]!r}) — give it a format in _LABELS"
            )


def test_the_guard_fires_on_an_undisclosed_difference():
    """A guard that cannot fail is decoration. Move a tranche's coupon between
    columns — the thing the pages promise never happens — and it must fail."""
    txu = next(c for c in CASES if c.slug.startswith("txu"))
    tampered = txu.realised.model_copy(deep=True)
    tampered.tranches[0].cash_rate += 0.01
    broken = type(txu)(**{**txu.__dict__, "realised": tampered})

    with pytest.raises(AssertionError, match="PRICING"):
        test_nothing_differs_outside_the_permitted_set(broken)

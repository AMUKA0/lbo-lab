"""When the PIK toggle gets elected.

A review finding: the engine elected only once a year had already failed, which
is once the revolver was exhausted. So it would burn the last of a facility at
the senior rate rather than accrue at the junior rate a year earlier. A
treasurer looking one year ahead decides differently — a drawn revolver is
precisely the facility you want available when the covenant conversation
starts.

These pin the new policy, and equally importantly pin what is NOT a trigger.
"""

import pytest

from lbo_engine import Covenants, run_lbo


def _toggled(deal, headroom: float = 0.0):
    d = deal.model_copy(deep=True)
    d.tranches[-1].pik_toggle = True
    d.pik_election_headroom = headroom
    return d


def _stressed(deal, headroom: float = 0.0):
    """Calibrated to the band where the option matters: enough pressure that the
    revolver gets drawn, not so much that nothing saves it."""
    d = _toggled(deal, headroom)
    d.operating.ebitda_margin = [0.192, 0.115, 0.11, 0.115, 0.125]
    d.revolver.commitment = 60.0
    return d


def _elected_years(result) -> list[int]:
    return [y.year for y in result.years if y.pik_elections]


class TestTheDefaultIsStillLastResort:
    def test_a_healthy_deal_never_elects(self, rich_deal):
        """Nobody PIKs a coupon they can afford — it steps the rate up and
        compounds."""
        assert _elected_years(run_lbo(_toggled(rich_deal))) == []

    def test_zero_headroom_preserves_the_old_behaviour(self, rich_deal):
        """The parameter defaults to nil, so an existing deal's schedule cannot
        move underneath anyone."""
        d = _stressed(rich_deal, headroom=0.0)
        assert d.pik_election_headroom == 0.0
        for y in run_lbo(d).years:
            if y.pik_elections:
                # Elected only where the alternative was failure, which means
                # the facility was already at the wall.
                assert y.revolver_closing > 0


class TestLookingAYearAhead:
    def test_headroom_makes_it_elect_earlier(self, rich_deal):
        late = run_lbo(_stressed(rich_deal, headroom=0.0))
        early = run_lbo(_stressed(rich_deal, headroom=0.5))

        assert _elected_years(early), "a headroom policy must actually elect"
        assert min(_elected_years(early)) <= min(_elected_years(late) or [99])
        assert len(_elected_years(early)) >= len(_elected_years(late))

    def test_it_leaves_more_of_the_revolver_undrawn(self, rich_deal):
        """The whole point. Accruing at the junior rate preserves the facility
        rather than spending it at the senior rate."""
        late = run_lbo(_stressed(rich_deal, headroom=0.0))
        early = run_lbo(_stressed(rich_deal, headroom=0.5))
        assert max(y.revolver_closing for y in early.years) < max(
            y.revolver_closing for y in late.years
        )

    def test_it_is_not_free(self, rich_deal):
        """Electing early buys liquidity with compounding principal at a stepped
        rate. A model where the option had no cost would be teaching the wrong
        lesson."""
        early = run_lbo(_stressed(rich_deal, headroom=0.5))
        late = run_lbo(_stressed(rich_deal, headroom=0.0))
        assert early.years[-1].total_debt_closing > late.years[-1].total_debt_closing


class TestWhatCountsAsAReason:
    def test_a_coverage_covenant_triggers_it(self, rich_deal):
        """PIK genuinely relieves the coverage test, because the test is struck
        on cash interest. So a borrower facing a coverage breach elects."""
        d = _toggled(rich_deal)
        d.tranches[-1].cash_rate = 0.11
        d.tranches[-1].pik_rate = 0.0
        d.covenants = Covenants(interest_coverage_floor=3.0)

        r = run_lbo(d)  # would breach in year one if it paid cash
        assert _elected_years(r), "the covenant must be a reason to elect"

    def test_a_leverage_covenant_does_not(self, rich_deal):
        """The one that would be wrong. Electing PIK accretes the coupon to
        principal and makes leverage WORSE, so toggling to cure a leverage
        breach is the opposite of a remedy. The engine must breach rather than
        reach for an option that cannot help."""
        from lbo_engine import CovenantBreach

        d = _toggled(rich_deal, headroom=0.5)
        d.covenants = Covenants(net_leverage_ceiling=3.0)
        with pytest.raises(CovenantBreach):
            run_lbo(d)

    def test_no_revolver_means_the_headroom_test_cannot_bind(self, rich_deal):
        """A structure with no facility has no headroom to preserve, and
        dividing by a nil commitment would be a silent error."""
        d = _toggled(rich_deal, headroom=0.9)
        d.revolver.commitment = 0.0
        assert _elected_years(run_lbo(d)) == []


class TestTheFallback:
    def test_a_year_that_can_only_be_paid_awkwardly_is_still_paid(self, rich_deal):
        """The policy is a preference, not a constraint. Refusing to model a
        year that can be paid at all — merely because it leaves the borrower
        uncomfortable — would be worse than paying it uncomfortably."""
        d = _stressed(rich_deal, headroom=0.95)  # unreachable comfort
        r = run_lbo(d)
        assert len(r.years) == d.hold_years
        # It reached for every option it had and still could not get comfortable,
        # and the year was modelled anyway rather than refused.
        eligible = [t.name for t in d.tranches if t.pik_toggle]
        assert any(len(y.pik_elections) == len(eligible) for y in r.years)
        assert any(
            d.revolver.commitment - y.revolver_closing
            < 0.95 * d.revolver.commitment
            for y in r.years
        )

"""The two failure modes that were missing.

The engine used to die one way: it ran out of cash. That is the rarer of the
real modes. Most 2008–09 sponsor distress was covenant-driven — the borrower
was still paying every coupon when the leverage test tripped — and TXU, the
largest buyout ever done, defaulted on a 2014 maturity wall rather than on a
missed payment.

These tests pin the distinctions that matter: that a breach is reported as a
breach and not as a shortfall, that the ratios are struck the way a credit
agreement strikes them, and that a wall assumed to be refinanced is an input
rather than something the engine quietly decides.
"""

import pytest

from lbo_engine import (
    Covenants,
    CovenantBreach,
    LiquidityFailure,
    MaturityWall,
    run_lbo,
)


class TestCovLiteIsTheDefault:
    def test_no_covenant_unless_one_is_set(self, rich_deal):
        """Not laziness — cov-lite is what the market actually issued from 2006
        onwards. Inventing a maintenance test where the credit agreement had
        none manufactures a default that never happened."""
        assert not rich_deal.covenants.any_test
        run_lbo(rich_deal)  # must not raise

    def test_a_generous_covenant_does_not_bind(self, rich_deal):
        d = rich_deal.model_copy(deep=True)
        d.covenants = Covenants(net_leverage_ceiling=10.0, interest_coverage_floor=1.0)
        run_lbo(d)


class TestTheLeverageTest:
    def _tight(self, deal, ceiling):
        d = deal.model_copy(deep=True)
        d.covenants = Covenants(net_leverage_ceiling=ceiling)
        return d

    def test_a_tight_ceiling_breaches(self, rich_deal):
        with pytest.raises(CovenantBreach) as exc:
            run_lbo(self._tight(rich_deal, 3.0))
        assert exc.value.year == 1
        assert exc.value.test == "net leverage"

    def test_it_is_a_breach_not_a_shortfall(self, rich_deal):
        """The distinction the whole feature exists for: this company is solvent
        and paying its coupons. Reporting it as 'ran out of cash' would be a
        different — and wrong — diagnosis."""
        with pytest.raises(CovenantBreach) as exc:
            run_lbo(self._tight(rich_deal, 3.0))
        assert not isinstance(exc.value, LiquidityFailure)
        assert exc.value.kind == "covenant"
        assert "still paying its coupons" in str(exc.value)

    def test_it_is_struck_NET_of_cash(self, rich_deal):
        """The agreement gives credit for the balance sheet, so a company can
        hold cash to stay inside its test. Gross leverage would breach here and
        net leverage does not."""
        d = self._tight(rich_deal, 5.0)
        d.cash_sweep_pct = 0.0  # pile cash up rather than repaying
        r = run_lbo(d)
        last = r.years[-1]
        assert last.closing_cash > 0
        gross = last.total_debt_closing / last.ebitda
        net = (last.total_debt_closing - last.closing_cash) / last.ebitda
        assert gross > net

    def test_a_step_down_schedule_tightens(self, rich_deal):
        """Real agreements ratchet. A ceiling that is comfortable at close and
        half a turn tighter each year is the normal shape."""
        d = rich_deal.model_copy(deep=True)
        d.covenants = Covenants(net_leverage_ceiling=[6.0, 5.5, 5.0, 4.5, 2.0])
        with pytest.raises(CovenantBreach) as exc:
            run_lbo(d)
        assert exc.value.year == 5, "only the final, tightest year should trip"


class TestTheCoverageTest:
    def test_a_high_floor_breaches(self, rich_deal):
        d = rich_deal.model_copy(deep=True)
        d.covenants = Covenants(interest_coverage_floor=5.0)
        with pytest.raises(CovenantBreach) as exc:
            run_lbo(d)
        assert exc.value.test == "interest coverage"

    def test_pik_does_not_count_against_coverage(self, rich_deal):
        """Cash interest only, because the test is about what must be PAID this
        period. This is exactly why a PIK toggle buys covenant headroom as well
        as liquidity, and why borrowers who saw a breach coming wanted one."""
        cash_pay = rich_deal.model_copy(deep=True)
        cash_pay.tranches[-1].cash_rate = 0.11
        cash_pay.tranches[-1].pik_rate = 0.0
        cash_pay.covenants = Covenants(interest_coverage_floor=3.0)

        accruing = cash_pay.model_copy(deep=True)
        accruing.tranches[-1].cash_rate = 0.0
        accruing.tranches[-1].pik_rate = 0.11

        with pytest.raises(CovenantBreach):
            run_lbo(cash_pay)
        run_lbo(accruing)  # identical economics, no cash coupon, no breach


class TestWhenTheTestIsApplied:
    def test_after_the_year_end_capital_events(self, rich_deal):
        """A divestiture completing in December is exactly how a borrower stays
        inside its leverage test. Testing before the proceeds land would report
        a breach the sponsor had already cured."""
        from lbo_engine import Divestiture

        d = rich_deal.model_copy(deep=True)
        d.covenants = Covenants(net_leverage_ceiling=4.6)
        with pytest.raises(CovenantBreach):
            run_lbo(d)

        rescued = d.model_copy(deep=True)
        rescued.divestitures = [Divestiture(year=1, proceeds=250.0, fee_pct=0.0)]
        run_lbo(rescued)


class TestTheMaturityWall:
    def _walled(self, deal, year: int, refinance: bool):
        d = deal.model_copy(deep=True)
        d.tranches[0].maturity_years = year
        d.tranches[0].refinance_at_maturity = refinance
        return d

    def test_refinancing_is_the_default_and_nothing_falls_due(self, rich_deal):
        """Most walls are refinanced. Assuming otherwise by default would make
        every model of a bullet loan fail in the year it matures."""
        assert all(t.refinance_at_maturity for t in rich_deal.tranches)
        run_lbo(self._walled(rich_deal, 3, refinance=True))

    def test_an_unrefinanced_wall_fails_as_a_wall(self, rich_deal):
        with pytest.raises(MaturityWall) as exc:
            run_lbo(self._walled(rich_deal, 3, refinance=False))
        assert exc.value.year == 3
        assert exc.value.tranche == rich_deal.tranches[0].name
        assert exc.value.kind == "maturity"
        assert "refinancing failure, not an operating one" in str(exc.value)

    def test_a_wall_the_company_can_actually_repay_is_not_a_failure(self, simple_deal):
        """Only unfunded maturities are walls. A tranche that has been swept
        down to something the balance sheet covers simply gets repaid."""
        d = simple_deal.model_copy(deep=True)
        d.hold_years = 3
        d.tranches[0].leverage_turns = 0.2  # trivially small
        d.tranches[0].maturity_years = 3
        d.tranches[0].refinance_at_maturity = False
        r = run_lbo(d)
        assert r.years[-1].tranches[d.tranches[0].name].closing == pytest.approx(0.0, abs=1e-9)

    def test_a_maturity_beyond_the_hold_never_binds(self, rich_deal):
        run_lbo(self._walled(rich_deal, rich_deal.hold_years + 3, refinance=False))

    def test_rolling_costs_the_refinancing_spread(self, rich_deal):
        """New money is priced at the market of the day it is raised, not the
        market the original deal was struck in — and only from the year AFTER
        the roll, since the old paper ran for the whole of its final year."""
        d = self._walled(rich_deal, 2, refinance=True)
        d.tranches[0].refinancing_spread = 0.03
        rolled = run_lbo(d)
        flat = run_lbo(self._walled(rich_deal, 2, refinance=True))

        name = d.tranches[0].name
        assert rolled.years[1].tranches[name].cash_interest == pytest.approx(
            flat.years[1].tranches[name].cash_interest, abs=1e-9
        ), "the maturity year itself is unaffected"
        assert rolled.years[2].tranches[name].cash_interest > (
            flat.years[2].tranches[name].cash_interest
        )


class TestTheFailuresStayCatchable:
    def test_every_failure_is_still_a_ValueError(self, rich_deal):
        """Callers that catch broadly — the API replays a partial run this way —
        must keep working. The type is additive information, not a new contract."""
        d = rich_deal.model_copy(deep=True)
        d.covenants = Covenants(net_leverage_ceiling=1.0)
        with pytest.raises(ValueError):
            run_lbo(d)

    def test_each_carries_the_year_it_broke(self, rich_deal):
        d = rich_deal.model_copy(deep=True)
        d.covenants = Covenants(net_leverage_ceiling=1.0)
        with pytest.raises(ValueError) as exc:
            run_lbo(d)
        assert exc.value.year == 1

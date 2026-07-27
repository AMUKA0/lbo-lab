"""Dividend recapitalisation.

The mechanic is small; the ways it can be got wrong are not. These tests pin the
three things that actually matter:

* the bridge identity still closes exactly, now against *total proceeds* rather
  than exit equity alone — the recap line has to carry gross debt raised, and a
  net-of-fee line would leave the identity short by exactly the fee;
* the economics come out the right way round — a recap lifts IRR and leaves MOIC
  flat to slightly *down*, because it creates no enterprise value and costs a
  fee plus incremental interest. A model showing MOIC rising on a recap has
  double-counted the proceeds;
* the incremental debt accrues no interest in its own year, which is the
  year-end convention the engine documents.
"""

import pytest

from lbo_engine import Assumptions, DividendRecap, run_lbo
from lbo_engine.returns import returns_bridge, sponsor_irr


def _with_recap(deal: Assumptions, **kwargs) -> Assumptions:
    # Re-validated rather than assigned: model-level validators only run on
    # construction, so mutating `.recaps` in place would skip every check.
    payload = deal.model_dump()
    payload["recaps"] = [DividendRecap(**kwargs).model_dump()]
    return Assumptions.model_validate(payload)


class TestIdentity:
    def test_bridge_reconciles_with_a_recap(self, rich_deal):
        deal = _with_recap(rich_deal, year=2, target_leverage_turns=5.0)
        b = returns_bridge(run_lbo(deal))
        assert b.recapitalisation > 0
        assert b.total_value_created == pytest.approx(
            b.total_proceeds - b.entry_equity, abs=1e-6
        )

    def test_bridge_reconciles_with_several_recaps(self, rich_deal):
        deal = rich_deal.model_copy(deep=True)
        deal.recaps = [
            DividendRecap(year=2, target_leverage_turns=5.0),
            DividendRecap(year=4, target_leverage_turns=4.5),
        ]
        b = returns_bridge(run_lbo(deal))
        assert b.total_value_created == pytest.approx(
            b.total_proceeds - b.entry_equity, abs=1e-6
        )

    def test_the_recap_line_is_gross_not_net(self, rich_deal):
        """Booking the net dividend instead of gross debt raised is the natural
        mistake, and it breaks the identity by exactly the financing fee."""
        deal = _with_recap(rich_deal, year=2, target_leverage_turns=5.0, financing_fee_pct=0.03)
        r = run_lbo(deal)
        b = returns_bridge(r)
        fee = sum(y.recap_fee for y in r.years)
        assert fee > 0
        assert b.recapitalisation == pytest.approx(r.total_dividends + fee, abs=1e-9)


class TestEconomics:
    def test_a_recap_lifts_irr_and_does_not_lift_moic(self, rich_deal):
        """The whole reason sponsors do this. Same total value, returned sooner:
        IRR rises, MOIC does not — it drifts down by the fee and the extra
        interest the new debt carries to exit."""
        base = run_lbo(rich_deal)
        recapped = run_lbo(_with_recap(rich_deal, year=2, target_leverage_turns=5.0))

        assert sponsor_irr(recapped) > sponsor_irr(base)
        assert recapped.moic < base.moic

    def test_moic_counts_dividends(self, rich_deal):
        r = run_lbo(_with_recap(rich_deal, year=2, target_leverage_turns=5.0))
        assert r.total_dividends > 0
        assert r.moic == pytest.approx(
            (r.total_dividends + r.exit_equity) / r.entry_equity
        )
        # Excluding them would understate the multiple on every recapped deal.
        assert r.moic > r.exit_equity / r.entry_equity

    def test_the_dividend_lands_in_the_year_it_is_paid(self, rich_deal):
        r = run_lbo(_with_recap(rich_deal, year=2, target_leverage_turns=5.0))
        flows = r.equity_cash_flows
        assert flows[2] == pytest.approx(r.years[1].recap_dividend)
        assert flows[1] == 0.0

    def test_earlier_recaps_are_worth_more(self, rich_deal):
        """Same mechanic, moved forward a year, must be worth more in IRR terms."""
        early = run_lbo(_with_recap(rich_deal, year=2, target_leverage_turns=5.0))
        late = run_lbo(_with_recap(rich_deal, year=4, target_leverage_turns=5.0))
        assert sponsor_irr(early) > sponsor_irr(late)


class TestMechanics:
    def test_new_debt_accrues_no_interest_in_its_own_year(self, rich_deal):
        """The year-end convention. If the recap year's interest moved, the debt
        would be earning a coupon for a period in which it did not exist."""
        base = run_lbo(rich_deal)
        recapped = run_lbo(_with_recap(rich_deal, year=2, target_leverage_turns=5.0))

        assert recapped.years[1].cash_interest_total == pytest.approx(
            base.years[1].cash_interest_total, abs=1e-9
        )
        # ...and it very much does from the next year on.
        assert recapped.years[2].cash_interest_total > base.years[2].cash_interest_total

    def test_target_leverage_is_hit_at_the_recap(self, rich_deal):
        deal = _with_recap(rich_deal, year=2, target_leverage_turns=5.0)
        r = run_lbo(deal)
        year = r.years[1]
        net_debt = year.total_debt_closing - year.closing_cash
        assert net_debt / year.ebitda == pytest.approx(5.0, abs=1e-6)

    def test_an_unfundable_recap_raises_nothing_and_says_so(self, rich_deal):
        """A target above current leverage means repaying debt, which is not a
        recap. It must be reported as raising nothing, not silently skipped and
        not crashed on."""
        r = run_lbo(_with_recap(rich_deal, year=2, target_leverage_turns=0.5))
        year = r.years[1]
        assert year.recap_target > 0
        assert year.recap_raised == 0.0
        assert year.recap_dividend == 0.0

    def test_a_fixed_amount_recap_raises_exactly_that(self, rich_deal):
        r = run_lbo(_with_recap(rich_deal, year=2, amount=100.0, financing_fee_pct=0.02))
        assert r.years[1].recap_raised == pytest.approx(100.0)
        assert r.years[1].recap_dividend == pytest.approx(98.0)

    def test_the_debt_lands_on_the_named_tranche(self, rich_deal):
        name = rich_deal.tranches[-1].name
        base = run_lbo(rich_deal)
        r = run_lbo(_with_recap(rich_deal, year=2, amount=100.0, tranche=name))
        assert r.years[1].tranches[name].closing == pytest.approx(
            base.years[1].tranches[name].closing + 100.0
        )


class TestValidation:
    def test_a_recap_needs_exactly_one_sizing_method(self):
        with pytest.raises(ValueError, match="exactly one"):
            DividendRecap(year=1)
        with pytest.raises(ValueError, match="exactly one"):
            DividendRecap(year=1, amount=100.0, target_leverage_turns=5.0)

    def test_a_recap_cannot_fall_outside_the_hold(self, rich_deal):
        with pytest.raises(ValueError, match="hold"):
            _with_recap(rich_deal, year=rich_deal.hold_years + 1, amount=100.0)

    def test_a_recap_cannot_name_an_unknown_tranche(self, rich_deal):
        with pytest.raises(ValueError, match="unknown tranche"):
            _with_recap(rich_deal, year=1, amount=100.0, tranche="not a tranche")

    def test_one_recap_per_year(self, rich_deal):
        payload = rich_deal.model_dump()
        payload["recaps"] = [
            DividendRecap(year=2, amount=50.0).model_dump(),
            DividendRecap(year=2, amount=60.0).model_dump(),
        ]
        with pytest.raises(ValueError, match="one dividend recap per year"):
            Assumptions.model_validate(payload)

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

from lbo_engine import Assumptions, Divestiture, DividendRecap, run_lbo
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


class TestPikToggle:
    """The PIK toggle: the issuer's option to accrue a coupon rather than pay
    it. Roughly a fifth of 2007 buyout firms used toggle debt, and it is the
    single most common reason a real structure survives a year a static model
    says it should not."""

    def _toggled(self, deal: Assumptions, premium: float = 0.0075) -> Assumptions:
        payload = deal.model_dump()
        payload["tranches"][-1]["pik_toggle"] = True
        payload["tranches"][-1]["pik_toggle_premium"] = premium
        return Assumptions.model_validate(payload)

    def _stressed(self, deal: Assumptions) -> Assumptions:
        """Calibrated to the band where the option is decisive: hard enough that
        the structure breaks without the toggle, survivable with it. At a 10%
        trough margin even the toggle cannot save it, which is the correct
        answer — the option buys room, not immunity."""
        payload = deal.model_dump()
        payload["operating"]["ebitda_margin"] = [0.192, 0.12, 0.115, 0.12, 0.13]
        payload["revolver"]["commitment"] = 20.0
        return Assumptions.model_validate(payload)

    def test_the_toggle_buys_room_but_not_immunity(self, rich_deal):
        """A deep enough trough breaks the structure with or without the option.
        Modelling it as a cure-all would be its own kind of dishonesty."""
        payload = self._stressed(rich_deal).model_dump()
        payload["operating"]["ebitda_margin"] = [0.192, 0.10, 0.095, 0.10, 0.11]
        hopeless = Assumptions.model_validate(payload)
        with pytest.raises(ValueError):
            run_lbo(self._toggled(hopeless))

    def test_the_toggle_is_not_used_when_cash_is_available(self, rich_deal):
        """Nobody PIKs a coupon they can afford — it steps the rate up and
        compounds. A toggle that fires on a healthy deal is a bug."""
        base = run_lbo(rich_deal)
        toggled = run_lbo(self._toggled(rich_deal))

        assert all(not y.pik_elections for y in toggled.years)
        assert toggled.moic == pytest.approx(base.moic)

    def test_the_toggle_rescues_a_year_that_would_otherwise_break(self, rich_deal):
        stressed = self._stressed(rich_deal)
        with pytest.raises(ValueError, match="revolver"):
            run_lbo(stressed)

        rescued = run_lbo(self._toggled(stressed))
        assert any(y.pik_elections for y in rescued.years)

    def test_electing_moves_the_coupon_from_cash_to_pik(self, rich_deal):
        r = run_lbo(self._toggled(self._stressed(rich_deal)))
        year = next(y for y in r.years if y.pik_elections)
        name = year.pik_elections[0]

        assert year.tranches[name].pik_elected
        assert year.tranches[name].cash_interest == 0.0
        assert year.tranches[name].pik_accrual > 0

    def test_the_step_up_is_charged(self, rich_deal):
        """The lender is compensated for waiting; a toggle at par would be a
        free option and no one would write it."""
        stressed = self._stressed(rich_deal)
        cheap = run_lbo(self._toggled(stressed, premium=0.0))
        dear = run_lbo(self._toggled(stressed, premium=0.05))

        cheap_year = next(y for y in cheap.years if y.pik_elections)
        dear_year = next((y for y in dear.years if y.pik_elections), None)
        assert dear_year is not None
        assert dear_year.pik_accrual_total > cheap_year.pik_accrual_total

    def test_junior_tranches_toggle_first(self, rich_deal):
        """Elections are searched cheapest-fix-first, and the junior paper is
        what carries the option in a real structure."""
        payload = self._stressed(rich_deal).model_dump()
        for t in payload["tranches"]:
            t["pik_toggle"] = True
        r = run_lbo(Assumptions.model_validate(payload))

        year = next(y for y in r.years if y.pik_elections)
        assert year.pik_elections == [rich_deal.tranches[-1].name]


class TestDivestitures:
    """Asset sales. The mirror image of a recap — cash in, debt down — and the
    mechanic without which any sum-of-the-parts underwriting reads as a deal
    that cannot service itself."""

    def _with_sale(self, deal: Assumptions, **kwargs) -> Assumptions:
        payload = deal.model_dump()
        payload["divestitures"] = [Divestiture(**kwargs).model_dump()]
        return Assumptions.model_validate(payload)

    def test_proceeds_repay_debt_net_of_fees(self, rich_deal):
        base = run_lbo(rich_deal)
        sold = run_lbo(self._with_sale(rich_deal, year=2, proceeds=200.0, fee_pct=0.01))

        year = sold.years[1]
        assert year.divestiture_proceeds == pytest.approx(198.0)
        assert year.divestiture_fees == pytest.approx(2.0)
        assert year.total_debt_closing < base.years[1].total_debt_closing

    def test_the_stack_is_repaid_senior_first(self, rich_deal):
        """Asset-sale proceeds are a mandatory prepayment, and that waterfall
        runs top down — not into whichever tranche is cheapest to retire."""
        senior, junior = (t.name for t in rich_deal.tranches)
        sold = run_lbo(self._with_sale(rich_deal, year=1, proceeds=100.0, fee_pct=0.0))
        base = run_lbo(rich_deal)

        year, base_year = sold.years[0], base.years[0]
        assert year.tranches[senior].closing < base_year.tranches[senior].closing
        assert year.tranches[junior].closing == pytest.approx(
            base_year.tranches[junior].closing
        )

    def test_a_sale_can_rescue_a_structure_that_would_not_finance(self, rich_deal):
        """The RJR case in miniature: the structure alone does not work, the
        structure plus the plan does."""
        payload = rich_deal.model_dump()
        payload["operating"]["ebitda_margin"] = [0.192, 0.115, 0.11, 0.115, 0.125]
        payload["revolver"]["commitment"] = 15.0
        stressed = Assumptions.model_validate(payload)
        with pytest.raises(ValueError):
            run_lbo(stressed)

        rescued = run_lbo(self._with_sale(stressed, year=1, proceeds=180.0))
        assert rescued.years[0].divestiture_proceeds > 0

    def test_surplus_beyond_the_whole_stack_becomes_cash(self, rich_deal):
        """Selling for more than the entire capital structure is worth must not
        drive a balance negative."""
        r = run_lbo(self._with_sale(rich_deal, year=1, proceeds=5000.0, fee_pct=0.0))
        year = r.years[0]
        assert year.total_debt_closing == pytest.approx(0.0, abs=1e-6)
        assert year.closing_cash > 1000
        assert all(t.closing >= 0 for t in year.tranches.values())

    def test_a_sale_cannot_fall_outside_the_hold(self, rich_deal):
        with pytest.raises(ValueError, match="hold"):
            self._with_sale(rich_deal, year=rich_deal.hold_years + 1, proceeds=100.0)


class TestLifecycle:
    """The lifecycle is a reading of a completed run, not a second model. Its
    only real failure mode is noise: a threshold that re-fires every year it is
    breached buries the events that represent an actual decision."""

    def _long_stress(self, deal: Assumptions) -> Assumptions:
        """Coverage below the watch level for the whole hold — the shape that
        used to produce one warning per year."""
        payload = deal.model_dump()
        payload["operating"]["ebitda_margin"] = [0.192, 0.10, 0.10, 0.10, 0.10]
        payload["revolver"]["commitment"] = 400.0
        return Assumptions.model_validate(payload)

    def test_a_sustained_breach_fires_once_not_every_year(self, rich_deal):
        from lbo_engine.analysis import lifecycle

        r = run_lbo(self._long_stress(rich_deal))
        events = lifecycle(r)

        coverage = [e for e in events if e.kind == "coverage"]
        # A crossing down, optionally a crossing back up, and at most one
        # low-water mark — never one per year of a five-year hold.
        assert len(coverage) <= 3, [e.title for e in coverage]
        years = [e.year for e in coverage]
        assert len(years) == len(set(years)), "two coverage events in the same year"

    def test_crossings_are_reported_in_both_directions(self, rich_deal):
        """A timeline that only marks bad news misrepresents the hold."""
        from lbo_engine.analysis import lifecycle

        payload = rich_deal.model_dump()
        # Coverage 3.17 -> 1.76 -> 1.82 -> 3.69 -> 4.81: down through the watch
        # level in year two, back above it in year four.
        payload["operating"]["ebitda_margin"] = [0.192, 0.10, 0.10, 0.19, 0.22]
        payload["revolver"]["commitment"] = 400.0
        events = lifecycle(run_lbo(Assumptions.model_validate(payload)))

        titles = " ".join(e.title for e in events if e.kind == "coverage")
        assert "falls through" in titles
        assert "recovers" in titles

    def test_a_healthy_deal_has_almost_no_events(self, rich_deal):
        """The base case should read as a straight line: a cheque and an exit."""
        from lbo_engine.analysis import lifecycle

        events = lifecycle(run_lbo(rich_deal))
        assert [e.kind for e in events] == ["entry", "exit"]

    def test_decisions_are_reported_every_time_they_happen(self, rich_deal):
        """Thresholds dedupe; *decisions* must not. Two recaps are two events."""
        from lbo_engine.analysis import lifecycle

        payload = rich_deal.model_dump()
        payload["recaps"] = [
            DividendRecap(year=2, target_leverage_turns=5.0).model_dump(),
            DividendRecap(year=4, target_leverage_turns=4.5).model_dump(),
        ]
        events = lifecycle(run_lbo(Assumptions.model_validate(payload)))
        assert len([e for e in events if e.kind == "recap"]) == 2

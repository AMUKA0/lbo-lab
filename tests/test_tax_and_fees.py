"""Tests for the literature-verified refinements: NOL carryforwards under the
80% limitation, financing-fee amortisation over the facility tenor (ASC
835-30), exit transaction costs, and the circularity-breaker toggle."""

import pytest

from lbo_engine import run_lbo
from lbo_engine.returns import returns_bridge, sponsor_irr


class TestNOLCarryforward:
    def _loss_deal(self, rich_deal):
        d = rich_deal.model_copy(deep=True)
        # Year 2 is a heavy loss; years 3+ recover and should be sheltered.
        d.operating.ebitda_margin = [0.192, 0.04, 0.198, 0.200, 0.202]
        d.revolver.commitment = 300.0
        return d

    def test_loss_year_creates_carryforward(self, rich_deal):
        r = run_lbo(self._loss_deal(rich_deal))
        loss_year = r.years[1]
        assert loss_year.ebt < 0
        assert loss_year.taxes == 0.0
        assert loss_year.nol_closing == pytest.approx(-loss_year.ebt, abs=1e-9)

    def test_carryforward_shelters_later_income(self, rich_deal):
        r = run_lbo(self._loss_deal(rich_deal))
        recovery = r.years[2]
        assert recovery.ebt > 0
        assert recovery.nol_used > 0
        # Tax is charged on income net of the NOL used, not on gross EBT.
        expected = (recovery.ebt - recovery.nol_used) * rich_deal.operating.tax_rate
        assert recovery.taxes == pytest.approx(expected, abs=1e-9)

    def test_eighty_percent_limitation_binds(self, rich_deal):
        """With a large enough NOL, only 80% of pre-tax income is sheltered —
        a profitable company still pays tax on the remaining 20% (§172(a))."""
        d = self._loss_deal(rich_deal)
        r = run_lbo(d)
        recovery = r.years[2]
        if recovery.nol_opening > 0.8 * recovery.ebt:  # limitation is binding
            assert recovery.nol_used == pytest.approx(0.8 * recovery.ebt, abs=1e-9)
            assert recovery.taxes > 0

    def test_nol_rollforward(self, rich_deal):
        r = run_lbo(self._loss_deal(rich_deal))
        for row in r.years:
            if row.ebt > 0:
                assert row.nol_closing == pytest.approx(row.nol_opening - row.nol_used, abs=1e-9)
            else:
                assert row.nol_closing == pytest.approx(row.nol_opening - row.ebt, abs=1e-9)

    def test_disabling_nols_raises_taxes(self, rich_deal):
        with_nol = self._loss_deal(rich_deal)
        without = with_nol.model_copy(deep=True)
        without.nol_limit_pct = 0.0
        assert sponsor_irr(run_lbo(with_nol)) > sponsor_irr(run_lbo(without))


class TestFinancingFeeTenor:
    def test_amortises_over_tenor_not_hold(self, rich_deal):
        """A 7-year facility on a 5-year hold expenses 1/7 per year, so part of
        the fee is never amortised before exit (ASC 835-30)."""
        r = run_lbo(rich_deal)
        expected = r.sources_uses.financing_fees / rich_deal.financing_fee_tenor_years
        assert r.years[0].fee_amortisation == pytest.approx(expected, abs=1e-9)

    def test_shorter_tenor_means_bigger_annual_charge(self, rich_deal):
        short = rich_deal.model_copy(deep=True)
        short.financing_fee_tenor_years = 3
        assert run_lbo(short).years[0].fee_amortisation > run_lbo(rich_deal).years[0].fee_amortisation


class TestExitFees:
    def test_exit_fees_reduce_proceeds(self, rich_deal):
        no_fee = rich_deal.model_copy(deep=True)
        no_fee.exit_fee_pct_ev = 0.0
        with_fee = run_lbo(rich_deal)
        assert with_fee.exit_fees == pytest.approx(0.01 * with_fee.exit_ev, abs=1e-9)
        assert with_fee.exit_equity < run_lbo(no_fee).exit_equity

    def test_bridge_still_reconciles_with_exit_fees(self, rich_deal):
        r = run_lbo(rich_deal)
        b = returns_bridge(r)
        assert b.total_value_created == pytest.approx(b.total_proceeds - r.entry_equity, abs=1e-6)


class TestCircularityBreaker:
    def test_opening_balance_mode_is_single_pass(self, rich_deal):
        d = rich_deal.model_copy(deep=True)
        d.interest_on_average_balance = False
        r = run_lbo(d)
        assert all(row.interest_iterations == 1 for row in r.years)

    def test_opening_balance_overstates_interest(self, rich_deal):
        """Charging on the opening balance ignores paydown during the year, so
        interest is higher and returns lower than the average-balance answer."""
        d = rich_deal.model_copy(deep=True)
        d.interest_on_average_balance = False
        opening_mode = run_lbo(d)
        average_mode = run_lbo(rich_deal)
        assert opening_mode.years[0].cash_interest_total > average_mode.years[0].cash_interest_total
        assert sponsor_irr(opening_mode) < sponsor_irr(average_mode)

    def test_two_conventions_stay_close(self, rich_deal):
        """The approximation should be materially small — a few hundred bps of
        interest, not a different deal."""
        d = rich_deal.model_copy(deep=True)
        d.interest_on_average_balance = False
        gap = abs(sponsor_irr(run_lbo(d)) - sponsor_irr(run_lbo(rich_deal)))
        assert gap < 0.03


class TestNolDirection:
    """`nol_limit_pct` is the share of a later year's income a carryforward may
    shelter, not the size of a restriction. The natural misreading — 0.0 as "no
    limitation" — silently disables the deduction entirely, so every case in the
    library once paid full cash tax on income its own comments said was
    sheltered. These pin the direction so it cannot invert again.
    """

    def _loss_then_profit(self, rich_deal):
        payload = rich_deal.model_dump()
        # A deep first year, then recovery: the only shape where NOLs bite.
        payload["operating"]["ebitda_margin"] = [0.10, 0.22, 0.22, 0.22, 0.22]
        return payload

    def test_full_carryforward_shelters_more_than_the_tcja_limit(self, rich_deal):
        from lbo_engine import Assumptions, run_lbo

        payload = self._loss_then_profit(rich_deal)
        taxes = {}
        for limit in (0.0, 0.8, 1.0):
            payload["nol_limit_pct"] = limit
            r = run_lbo(Assumptions.model_validate(payload))
            taxes[limit] = r.years[1].taxes
            assert r.years[0].nol_closing > 0, "year one must generate a carryforward"

        # More shelter allowed => less tax paid. Never the other way round.
        assert taxes[0.0] > taxes[0.8] >= taxes[1.0]

    def test_zero_means_no_deduction_not_no_limitation(self, rich_deal):
        """The exact misreading that caused the bug: at 0.0 a carryforward
        exists on the balance sheet and can never be used."""
        from lbo_engine import Assumptions, run_lbo

        payload = self._loss_then_profit(rich_deal)
        payload["nol_limit_pct"] = 0.0
        r = run_lbo(Assumptions.model_validate(payload))

        assert r.years[0].nol_closing > 0
        assert all(y.nol_used == 0.0 for y in r.years)
        # ...and the carryforward just accumulates, never relieving anything.
        assert r.years[-1].nol_closing >= r.years[0].nol_closing

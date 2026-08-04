"""Analysis-layer tests: the grid must be monotonic in the directions
economics dictates, and must show NaN (not a fabricated number) where the
structure fails."""

import math

import pytest

from lbo_engine.analysis import debt_paydown_table, entry_exit_sensitivity
from lbo_engine.engine import run_lbo
from lbo_engine.returns import sponsor_irr


class TestSensitivityGrid:
    def test_center_cell_matches_direct_run(self, rich_deal):
        grid = entry_exit_sensitivity(rich_deal, [11.0], [11.5])
        direct = sponsor_irr(run_lbo(rich_deal))
        assert grid.loc[11.0, 11.5] == pytest.approx(direct, abs=1e-9)

    def test_irr_rises_with_exit_multiple(self, rich_deal):
        grid = entry_exit_sensitivity(rich_deal, [11.0], [9.0, 10.0, 11.0, 12.0, 13.0])
        values = grid.loc[11.0].tolist()
        assert values == sorted(values)

    def test_irr_falls_as_entry_price_rises(self, rich_deal):
        grid = entry_exit_sensitivity(rich_deal, [9.0, 10.0, 11.0, 12.0], [11.5])
        values = grid[11.5].tolist()
        assert values == sorted(values, reverse=True)

    def test_failed_structures_are_nan(self, rich_deal):
        # An absurdly cheap exit on a fully levered entry wipes the sponsor.
        grid = entry_exit_sensitivity(rich_deal, [11.0], [1.0])
        assert math.isnan(grid.loc[11.0, 1.0])


class TestDebtPaydownTable:
    def test_year_zero_is_sources_and_uses(self, rich_deal):
        table = debt_paydown_table(rich_deal)
        r = run_lbo(rich_deal)
        assert table.loc[0, "senior_tl"] == pytest.approx(r.sources_uses.tranche_amounts["senior_tl"])
        assert table.loc[0, "cash"] == pytest.approx(rich_deal.minimum_cash)

    def test_final_year_matches_engine(self, rich_deal):
        table = debt_paydown_table(rich_deal)
        r = run_lbo(rich_deal)
        last = r.years[-1]
        assert table.loc[rich_deal.hold_years, "senior_tl"] == pytest.approx(
            last.tranches["senior_tl"].closing
        )


class TestEarlyExitsDropLaterEvents:
    """A recap in year four cannot have happened if you sold in year three.

    The previous version set `hold_years` by attribute assignment, which
    bypasses Pydantic's re-validation, so an event past the shortened hold
    simply never fired — no crash, no note, and a quietly understated IRR on
    the one case where it mattered.
    """

    def test_a_recap_beyond_the_exit_is_removed_not_ignored(self, rich_deal):
        from lbo_engine import DividendRecap
        from lbo_engine.analysis import exit_year_profile

        deal = rich_deal.model_copy(deep=True)
        deal.recaps = [DividendRecap(year=4, amount=60.0)]
        profile = exit_year_profile(deal)

        # Selling in year 2 or 3 predates the recap; 4 and 5 include it.
        assert not profile["moic"].isna().any(), "every early exit must still model"

    def test_the_recap_lifts_the_years_that_contain_it(self, rich_deal):
        from lbo_engine import DividendRecap
        from lbo_engine.analysis import exit_year_profile

        plain = exit_year_profile(rich_deal)
        with_recap = rich_deal.model_copy(deep=True)
        with_recap.recaps = [DividendRecap(year=4, amount=60.0)]
        recapped = exit_year_profile(with_recap)

        # Year 3 predates it, so nothing moves. Year 4 contains it, so it does.
        assert recapped.loc[3, "irr"] == pytest.approx(plain.loc[3, "irr"], abs=1e-9)
        assert recapped.loc[4, "irr"] != pytest.approx(plain.loc[4, "irr"], abs=1e-9)

    def test_covenant_schedules_are_truncated_too(self, rich_deal):
        """The shared truncation handles every per-year schedule, so a covenant
        step-down does not make an early exit reject for a length mismatch."""
        from lbo_engine import Covenants
        from lbo_engine.analysis import exit_year_profile

        deal = rich_deal.model_copy(deep=True)
        deal.covenants = Covenants(net_leverage_ceiling=[9.0, 8.5, 8.0, 7.5, 7.0])
        assert not exit_year_profile(deal)["moic"].isna().any()


class TestTheTornadoCoversTheCreditMarket:
    def test_cost_of_debt_is_a_driver(self, rich_deal):
        from lbo_engine.analysis import tornado

        assert any("Cost of debt" in str(i) for i in tornado(rich_deal).index)

    def test_it_moves_the_answer_more_than_the_tax_rate(self, rich_deal):
        """The review's specific comparison: on a levered structure ±100bp of
        credit spread is a bigger and likelier swing than ±5pts of tax, and it
        is the one input the sponsor does not control."""
        from lbo_engine.analysis import tornado

        df = tornado(rich_deal)
        spans = {str(i): abs(r.high_irr - r.low_irr) for i, r in df.iterrows()}
        debt = next(v for k, v in spans.items() if "Cost of debt" in k)
        tax = next(v for k, v in spans.items() if "Tax rate" in k)
        assert debt > tax, f"cost of debt {debt:.2%} vs tax {tax:.2%}"

    def test_it_handles_a_coupon_that_is_already_a_path(self, rich_deal):
        """Shifting a driver must not turn a per-year path into a scalar."""
        from lbo_engine import Assumptions
        from lbo_engine.analysis import tornado

        payload = rich_deal.model_dump()
        payload["tranches"][0]["cash_rate"] = [0.05, 0.05, 0.06, 0.06, 0.07]
        deal = Assumptions.model_validate(payload)
        assert any("Cost of debt" in str(i) for i in tornado(deal).index)

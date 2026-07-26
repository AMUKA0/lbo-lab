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

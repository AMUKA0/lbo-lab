"""Credit-stats and exit-timing tests: ratios tie to the engine's schedule,
deleveraging shows up as falling leverage and rising coverage, and the exit
profile matches direct runs."""

import pytest

from lbo_engine.analysis import credit_stats, exit_year_profile
from lbo_engine.engine import run_lbo
from lbo_engine.returns import sponsor_irr


class TestCreditStats:
    def test_ratios_tie_to_schedule(self, rich_deal):
        stats = credit_stats(rich_deal)
        r = run_lbo(rich_deal)
        first = r.years[0]
        net_debt = first.total_debt_closing - first.closing_cash
        assert stats.loc[1, "net_leverage"] == pytest.approx(net_debt / first.ebitda)
        assert stats.loc[1, "interest_coverage"] == pytest.approx(
            first.ebitda / first.cash_interest_total
        )

    def test_deal_delevers(self, rich_deal):
        stats = credit_stats(rich_deal)
        assert stats["net_leverage"].iloc[-1] < stats["net_leverage"].iloc[0]
        assert stats["interest_coverage"].iloc[-1] > stats["interest_coverage"].iloc[0]

    def test_coverage_ordering(self, rich_deal):
        # EBITDA-less-capex coverage must sit below plain EBITDA coverage.
        stats = credit_stats(rich_deal)
        assert (stats["ebitda_less_capex_coverage"] < stats["interest_coverage"]).all()


class TestExitYearProfile:
    def test_final_year_matches_base_run(self, rich_deal):
        profile = exit_year_profile(rich_deal)
        base_irr = sponsor_irr(run_lbo(rich_deal))
        assert profile.loc[rich_deal.hold_years, "irr"] == pytest.approx(base_irr, abs=1e-9)

    def test_moic_rises_with_hold(self, rich_deal):
        # With positive FCF and a fixed exit multiple, staying in longer
        # keeps compounding EBITDA and paying down debt: MOIC must rise.
        profile = exit_year_profile(rich_deal)
        moics = profile["moic"].tolist()
        assert moics == sorted(moics)

    def test_covers_years_two_through_hold(self, rich_deal):
        profile = exit_year_profile(rich_deal)
        assert list(profile.index) == list(range(2, rich_deal.hold_years + 1))

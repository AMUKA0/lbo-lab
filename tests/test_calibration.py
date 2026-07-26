"""Calibration and analysis-layer tests: flags fire when they should and stay
quiet when they shouldn't; the tornado ranks the drivers economics says it
must; the breakeven solver inverts the model correctly."""

import math

import pytest

from lbo_engine.analysis import (
    apply_recession,
    breakeven_exit_multiple,
    scenario_set,
    tornado,
)
from lbo_engine.calibration import check_assumptions
from lbo_engine.engine import run_lbo
from lbo_engine.returns import sponsor_irr


class TestGuardrails:
    def test_reasonable_deal_flags_only_expansion(self, rich_deal):
        # rich_deal exits above entry (11.5 vs 11) — that flag SHOULD fire;
        # everything else is inside market bands.
        flags = check_assumptions(rich_deal)
        assert [f.field for f in flags] == ["exit_multiple"]

    def test_high_leverage_flags_amber(self, rich_deal):
        hot = rich_deal.model_copy(deep=True)
        hot.tranches[0].leverage_turns = 5.5  # total 7.0x with the mezz
        flags = {f.field: f for f in check_assumptions(hot)}
        assert flags["leverage"].level == "amber"

    def test_premium_entry_flags(self, rich_deal):
        rich = rich_deal.model_copy(deep=True)
        rich.entry_multiple = 14.0
        rich.exit_multiple = 14.0
        fields = {f.field for f in check_assumptions(rich)}
        assert "entry_multiple" in fields

    def test_heroic_growth_flags(self, rich_deal):
        hero = rich_deal.model_copy(deep=True)
        hero.operating.revenue_growth = 0.15
        fields = {f.field for f in check_assumptions(hero)}
        assert "revenue_growth" in fields

    def test_every_flag_carries_a_source(self, rich_deal):
        wild = rich_deal.model_copy(deep=True)
        wild.entry_multiple = 15.0
        wild.operating.revenue_growth = 0.20
        wild.tranches[0].leverage_turns = 6.0
        for flag in check_assumptions(wild):
            assert flag.source, f"flag {flag.field} has no source"


class TestTornado:
    def test_exit_multiple_dominates_tax(self, rich_deal):
        t = tornado(rich_deal)
        spans = (t["high_irr"] - t["low_irr"]).abs()
        assert spans["Exit multiple (±1.0×)"] > spans["Tax rate (±5pts)"]

    def test_sorted_widest_first(self, rich_deal):
        t = tornado(rich_deal)
        spans = (t["high_irr"] - t["low_irr"]).abs().tolist()
        assert spans == sorted(spans, reverse=True)

    def test_upside_is_up_and_downside_is_down(self, rich_deal):
        t = tornado(rich_deal)
        base = t["base_irr"].iloc[0]
        for driver, row in t.iterrows():
            assert row["low_irr"] <= base + 1e-9, driver
            assert row["high_irr"] >= base - 1e-9, driver


class TestScenarios:
    def test_ordering(self, rich_deal):
        results = {
            name: sponsor_irr(run_lbo(a)) for name, a in scenario_set(rich_deal).items()
        }
        assert results["Upside"] > results["Base"] > results["Downside"]
        # The recession stress must hurt, but it need not rank below the
        # downside case: the recession is V-shaped (margins fully recover, so
        # terminal EBITDA is intact and only the exit multiple is hit), while
        # the downside is a PERMANENT growth/margin downgrade that compounds
        # into exit-year EBITDA. A sharp-but-temporary shock genuinely can
        # beat a slow permanent one — that asymmetry is a feature, not a bug.
        assert results["Recession stress"] < results["Base"]

    def test_recession_shocks_early_years_only(self, rich_deal):
        stressed = apply_recession(rich_deal, ebitda_shock=0.2, shock_years=2)
        base_m = rich_deal.margin_schedule()
        new_m = stressed.margin_schedule()
        assert new_m[0] == pytest.approx(base_m[0] * 0.8)
        assert new_m[1] == pytest.approx(base_m[1] * 0.8)
        assert new_m[2:] == pytest.approx(base_m[2:])
        assert stressed.exit_multiple == pytest.approx(rich_deal.exit_multiple - 1.5)


class TestBreakeven:
    def test_solved_multiple_hits_target(self, rich_deal):
        target = 0.20
        multiple = breakeven_exit_multiple(rich_deal, target)
        check = rich_deal.model_copy(deep=True)
        check.exit_multiple = multiple
        assert sponsor_irr(run_lbo(check)) == pytest.approx(target, abs=1e-4)

    def test_higher_target_needs_higher_multiple(self, rich_deal):
        assert breakeven_exit_multiple(rich_deal, 0.25) > breakeven_exit_multiple(rich_deal, 0.15)

    def test_unreachable_target_is_nan(self, rich_deal):
        assert math.isnan(breakeven_exit_multiple(rich_deal, 5.0))

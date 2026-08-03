"""Engine tests.

The golden case is solved by hand: with flat EBITDA E, one bullet tranche at
rate r, full sweep and no taxes/fees/capex, each year's interest satisfies
    I = r × (opening + closing)/2,  closing = opening − (E − I)
which gives the closed form  I = r(opening − E/2) / (1 − r/2).
Every balance below comes from iterating that identity with E=100, r=5%.
"""

import pytest

from lbo_engine import InterestLimitation, run_lbo
from lbo_engine.returns import returns_bridge, sponsor_irr

# Golden path for the simple deal (opening debt 400):
#   I1 = 0.05×(400−50)/0.975 = 17.948718  → closing 317.948718
#   I2 = 0.05×(317.948718−50)/0.975       → closing 231.689678
#   I3 = 0.05×(231.689678−50)/0.975       → closing 141.007097
GOLDEN = [
    (17.948718, 317.948718),
    (13.740960, 231.689678),
    (9.317419, 141.007097),
]


class TestGoldenCase:
    def test_debt_schedule_matches_hand_calculation(self, simple_deal):
        r = run_lbo(simple_deal)
        for row, (interest, closing) in zip(r.years, GOLDEN):
            t = row.tranches["senior"]
            assert t.cash_interest == pytest.approx(interest, abs=1e-6)
            assert t.closing == pytest.approx(closing, abs=1e-6)

    def test_exit_and_returns(self, simple_deal):
        r = run_lbo(simple_deal)
        assert r.exit_ev == pytest.approx(1000.0)
        assert r.exit_equity == pytest.approx(1000.0 - 141.007097, abs=1e-6)
        assert r.entry_equity == pytest.approx(600.0)
        assert r.moic == pytest.approx(858.992903 / 600.0, abs=1e-6)
        # Single in/out flow: IRR must equal MOIC^(1/n) − 1 exactly.
        assert sponsor_irr(r) == pytest.approx(r.moic ** (1 / 3) - 1, abs=1e-8)

    def test_interest_solve_converges_fast(self, simple_deal):
        r = run_lbo(simple_deal)
        assert all(row.interest_iterations < 50 for row in r.years)


class TestInvariants:
    """Identities that must hold for ANY valid deal."""

    def test_sources_equal_uses(self, rich_deal):
        su = run_lbo(rich_deal).sources_uses
        assert su.total_sources == pytest.approx(su.total_uses, abs=1e-9)

    def test_debt_rollforward(self, rich_deal):
        """closing = opening + PIK − mandatory − sweep, every tranche, every year."""
        r = run_lbo(rich_deal)
        for row in r.years:
            for t in row.tranches.values():
                expected = t.opening + t.pik_accrual - t.mandatory_repayment - t.sweep_repayment
                assert t.closing == pytest.approx(expected, abs=1e-9)

    def test_cash_never_below_minimum(self, rich_deal):
        r = run_lbo(rich_deal)
        for row in r.years:
            assert row.closing_cash >= rich_deal.minimum_cash - 1e-9

    def test_balances_never_negative(self, rich_deal):
        r = run_lbo(rich_deal)
        for row in r.years:
            assert row.revolver_closing >= -1e-9
            for t in row.tranches.values():
                assert t.closing >= -1e-9

    def test_bridge_sums_exactly_to_equity_gain(self, rich_deal):
        r = run_lbo(rich_deal)
        b = returns_bridge(r)
        # The general identity: the bridge sums to the sponsor's TOTAL proceeds
        # (exit equity plus any recap dividends) less the entry cheque. With no
        # recaps this reduces to the equity gain.
        assert b.total_value_created == pytest.approx(b.total_proceeds - r.entry_equity, abs=1e-6)

    def test_mandatory_amort_is_pct_of_original_principal(self, rich_deal):
        r = run_lbo(rich_deal)
        original = r.sources_uses.tranche_amounts["senior_tl"]
        first_year = r.years[0].tranches["senior_tl"]
        assert first_year.mandatory_repayment == pytest.approx(0.05 * original, abs=1e-9)

    def test_pik_accrues_on_opening_balance(self, rich_deal):
        r = run_lbo(rich_deal)
        for row in r.years:
            mezz = row.tranches["mezzanine"]
            assert mezz.pik_accrual == pytest.approx(0.03 * mezz.opening, abs=1e-9)

    def test_non_sweepable_tranche_never_swept(self, rich_deal):
        r = run_lbo(rich_deal)
        for row in r.years:
            assert row.tranches["mezzanine"].sweep_repayment == 0.0


class TestStressBehaviour:
    def test_shortfall_draws_revolver(self, rich_deal):
        stressed = rich_deal.model_copy(deep=True)
        stressed.operating.ebitda_margin = [0.192, 0.09, 0.09, 0.20, 0.202]
        stressed.revolver.commitment = 200.0  # ample headroom: we want a draw, not a failure
        r = run_lbo(stressed)
        assert any(row.revolver_draw > 0 for row in r.years)
        # Cash never dips below the floor even in the trough years.
        assert all(row.closing_cash >= stressed.minimum_cash - 1e-9 for row in r.years)

    def test_structure_fails_loudly_when_revolver_exhausted(self, rich_deal):
        broken = rich_deal.model_copy(deep=True)
        broken.operating.ebitda_margin = 0.01  # EBITDA collapses; interest overwhelms cash
        with pytest.raises(ValueError, match="structure fails"):
            run_lbo(broken)

    def test_taxes_floored_at_zero_in_loss_years(self, rich_deal):
        stressed = rich_deal.model_copy(deep=True)
        stressed.operating.ebitda_margin = [0.192, 0.05, 0.198, 0.200, 0.202]
        # A tax loss, not merely a book loss: with §163(j) on, a year can be
        # loss-making and still owe tax, which is a different property and is
        # tested separately.
        stressed.interest_limitation = InterestLimitation(enabled=False)
        r = run_lbo(stressed)
        loss_year = r.years[1]
        assert loss_year.ebt < 0
        assert loss_year.taxable_income < 0
        assert loss_year.taxes == 0.0

    def test_no_sweep_bullet_builds_cash_instead(self, simple_deal):
        hoard = simple_deal.model_copy(deep=True)
        hoard.cash_sweep_pct = 0.0
        r = run_lbo(hoard)
        assert r.years[-1].tranches["senior"].closing == pytest.approx(400.0)
        assert r.years[-1].closing_cash > 0
        # Hoarded cash earns nothing while debt accrues 5%, so sweeping must
        # end with strictly lower net debt — the whole point of the sweep.
        swept = run_lbo(simple_deal)
        assert swept.exit_net_debt < r.exit_net_debt

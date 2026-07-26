"""IRR solver and returns-bridge unit tests with known answers."""

import pytest

from lbo_engine.returns import irr, npv


class TestIRR:
    def test_known_two_period(self):
        # -100 today, +121 in two years → exactly 10%.
        assert irr([-100.0, 0.0, 121.0]) == pytest.approx(0.10, abs=1e-8)

    def test_known_single_period(self):
        assert irr([-100.0, 125.0]) == pytest.approx(0.25, abs=1e-8)

    def test_typical_lbo_shape(self):
        # 2.5x over 5 years → (2.5)^(1/5) − 1 ≈ 20.11%
        assert irr([-100.0, 0, 0, 0, 0, 250.0]) == pytest.approx(2.5 ** 0.2 - 1, abs=1e-8)

    def test_negative_irr(self):
        # Losing half the money over 3 years.
        assert irr([-100.0, 0, 0, 50.0]) == pytest.approx(0.5 ** (1 / 3) - 1, abs=1e-8)

    def test_npv_at_irr_is_zero(self):
        flows = [-100.0, 30.0, 40.0, 50.0, 20.0]
        assert npv(irr(flows), flows) == pytest.approx(0.0, abs=1e-6)

    def test_rejects_all_positive(self):
        with pytest.raises(ValueError):
            irr([100.0, 50.0])

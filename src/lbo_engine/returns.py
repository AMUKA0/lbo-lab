"""Returns: IRR, MOIC and the value-creation bridge.

IRR is solved by bisection on the NPV of the sponsor's equity cash flows —
robust for LBO-shaped flows (one outflow, later inflows: a unique sign change
guarantees a unique real IRR above -100%).

The bridge decomposes the equity gain into the three standard drivers, plus
the fee drag, using the conventional attribution:

  EBITDA growth       = (exit EBITDA − entry EBITDA) × entry multiple
  Multiple expansion  = (exit multiple − entry multiple) × exit EBITDA
  Deleveraging        = entry net debt − exit net debt
  Fee drag            = −(transaction fees + financing fees + exit fees)

These four terms sum EXACTLY to (exit equity − entry equity) — an identity the
test suite asserts. (The growth/multiple split has a known convention choice:
the cross term (ΔEBITDA × Δmultiple) sits in the multiple line here, the most
common treatment.)
"""

from __future__ import annotations

from dataclasses import dataclass

from lbo_engine.engine import LBOResult


def npv(rate: float, flows: list[float]) -> float:
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(flows))


def irr(flows: list[float], *, low: float = -0.9999, high: float = 100.0, tol: float = 1e-10) -> float:
    """Bisection IRR. Requires at least one negative and one positive flow."""
    if not any(cf < 0 for cf in flows) or not any(cf > 0 for cf in flows):
        raise ValueError("IRR requires both negative and positive cash flows")
    f_low, f_high = npv(low, flows), npv(high, flows)
    if f_low * f_high > 0:
        raise ValueError("IRR not bracketed in (-99.99%, 10000%)")
    for _ in range(200):
        mid = 0.5 * (low + high)
        f_mid = npv(mid, flows)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return 0.5 * (low + high)


@dataclass(frozen=True)
class ReturnsBridge:
    ebitda_growth: float
    multiple_expansion: float
    deleveraging: float
    fee_drag: float
    entry_equity: float
    exit_equity: float

    @property
    def total_value_created(self) -> float:
        return self.ebitda_growth + self.multiple_expansion + self.deleveraging + self.fee_drag


def returns_bridge(r: LBOResult) -> ReturnsBridge:
    a = r.assumptions
    su = r.sources_uses
    return ReturnsBridge(
        ebitda_growth=(r.exit_ebitda - a.entry_ebitda) * a.entry_multiple,
        multiple_expansion=(a.exit_multiple - a.entry_multiple) * r.exit_ebitda,
        deleveraging=r.entry_net_debt - r.exit_net_debt,
        fee_drag=-(su.transaction_fees + su.financing_fees + r.exit_fees),
        entry_equity=r.entry_equity,
        exit_equity=r.exit_equity,
    )


def sponsor_irr(r: LBOResult) -> float:
    return irr(r.equity_cash_flows)

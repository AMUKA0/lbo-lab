"""Returns: IRR, MOIC and the value-creation bridge.

IRR is solved by bisection on the NPV of the sponsor's equity cash flows —
robust for LBO-shaped flows (one outflow, later inflows: a unique sign change
guarantees a unique real IRR above -100%).

The bridge decomposes the equity gain into the three standard drivers, plus
the fee drag, using the conventional attribution:

  EBITDA growth       = (exit EBITDA − entry EBITDA) × entry multiple
  Multiple expansion  = (exit multiple − entry multiple) × exit EBITDA
  Deleveraging        = entry net debt − exit net debt
  Recapitalisation    = gross incremental debt raised in dividend recaps
  Fee drag            = −(transaction + financing + recap + exit fees)

These terms sum EXACTLY to the sponsor's total value created — exit equity plus
recap dividends, less the entry cheque — an identity the test suite asserts.

The recap line carries the **gross** debt raised, not the net dividend, and that
is forced rather than chosen. A recap adds N to exit net debt (shrinking the
deleveraging line by N) and F to fees, while paying the sponsor N − F. Booking
the net dividend instead leaves the identity short by exactly the fee; booking
the gross closes it. Note also what the line is *not*: a recap creates no
enterprise value. It converts future equity into present cash and buys that with
interest cost, which is why it moves IRR far more than it moves MOIC. (The growth/multiple split has a known convention choice:
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
    recapitalisation: float
    fee_drag: float
    entry_equity: float
    exit_equity: float
    dividends: float

    @property
    def total_value_created(self) -> float:
        return (
            self.ebitda_growth
            + self.multiple_expansion
            + self.deleveraging
            + self.recapitalisation
            + self.fee_drag
        )

    @property
    def total_proceeds(self) -> float:
        """What the sponsor actually gets back: exit equity plus recap dividends."""
        return self.exit_equity + self.dividends


def returns_bridge(r: LBOResult) -> ReturnsBridge:
    a = r.assumptions
    su = r.sources_uses
    recap_fees = sum(y.recap_fee for y in r.years)
    return ReturnsBridge(
        ebitda_growth=(r.exit_ebitda - a.entry_ebitda) * a.entry_multiple,
        multiple_expansion=(a.exit_multiple - a.entry_multiple) * r.exit_ebitda,
        deleveraging=r.entry_net_debt - r.exit_net_debt,
        recapitalisation=sum(y.recap_raised for y in r.years),
        fee_drag=-(su.transaction_fees + su.financing_fees + recap_fees + r.exit_fees),
        entry_equity=r.entry_equity,
        exit_equity=r.exit_equity,
        dividends=r.total_dividends,
    )


def sponsor_irr(r: LBOResult) -> float:
    return irr(r.equity_cash_flows)

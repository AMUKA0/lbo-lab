"""The ways a structure can fail, as distinct types.

Until now the engine had one failure: it ran out of cash. That is the *rarer*
of the real modes. Most 2008–09 sponsor distress was covenant-driven — the
company was still paying its bills when the leverage test tripped — and TXU,
the largest buyout ever done, died on a 2014 maturity wall rather than on a
missed coupon.

All three subclass `ValueError`, so callers that already catch broadly keep
working; the type is there for callers that want to say *which* wall was hit,
because "breaks in year three" and "breaches its leverage covenant in year
three while still solvent" are different findings with different remedies.
"""

from __future__ import annotations


class StructureFailure(ValueError):
    """The structure cannot be modelled through to exit.

    Carries the year so a caller can replay the years that did work rather than
    discarding the whole run — a credit committee wants the schedule up to the
    break, not the word "failed".
    """

    kind = "failure"

    def __init__(self, year: int, message: str):
        self.year = year
        super().__init__(message)


class LiquidityFailure(StructureFailure):
    """Out of cash: a shortfall larger than the undrawn revolver."""

    kind = "liquidity"

    def __init__(self, year: int, shortfall: float, capacity: float):
        self.shortfall = shortfall
        self.capacity = capacity
        super().__init__(
            year,
            f"Year {year}: cash shortfall of {shortfall:,.1f} exceeds undrawn revolver "
            f"capacity of {capacity:,.1f} — the structure fails. Reduce leverage, add "
            "revolver commitment, or revisit operating assumptions.",
        )


class CovenantBreach(StructureFailure):
    """A maintenance covenant tripped.

    Solvency is not the question here — the company may be paying every coupon
    on time. A maintenance covenant is tested on a ratio, and breaching it is an
    event of default that hands the lenders the keys unless it is waived, cured
    or amended. In practice it is almost always one of those three, at a price;
    the engine reports the breach and leaves the remedy to be modelled
    explicitly as sponsor support.
    """

    kind = "covenant"

    def __init__(self, year: int, test: str, required: str, actual: str):
        self.test = test
        self.required = required
        self.actual = actual
        super().__init__(
            year,
            f"Year {year}: {test} covenant breached — {actual} against a required "
            f"{required}. The company is still paying its coupons; the ratio is what "
            "failed. A real borrower would seek a waiver, an amendment, or an equity "
            "cure, each of which costs something the model does not assume for free.",
        )


class MaturityWall(StructureFailure):
    """A tranche came due inside the hold with no way to repay it.

    The failure mode that killed TXU: the business was servicing its interest,
    but a wall of principal fell due in a market that would not refinance it.
    Distinct from a liquidity failure because the remedy is different — this is
    solved in the capital markets, not by trading better.
    """

    kind = "maturity"

    def __init__(self, year: int, tranche: str, amount: float, available: float):
        self.tranche = tranche
        self.amount = amount
        self.available = available
        super().__init__(
            year,
            f"Year {year}: {amount:,.1f} of {tranche} matures and only {available:,.1f} "
            "is available to repay it. The business was servicing its interest — this is "
            "a refinancing failure, not an operating one. Mark the tranche as refinanced "
            "at maturity if the market would have taken it.",
        )

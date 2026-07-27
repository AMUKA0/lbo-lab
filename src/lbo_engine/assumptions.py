"""Typed, validated deal assumptions.

Conventions follow standard sponsor-model practice:
- The transaction is cash-free / debt-free: the buyer purchases the enterprise,
  existing debt is refinanced at close, and any opening cash is funded in Uses.
- Leverage is expressed in turns of entry EBITDA per tranche.
- Mandatory amortisation is a percentage of ORIGINAL principal per year
  (term-loan convention), not of the outstanding balance.
- Growth/margin inputs may be a single number (held flat) or a per-year list.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


def _as_schedule(value: float | list[float], years: int, name: str) -> list[float]:
    """Expand a scalar to a per-year list, or validate a provided list's length."""
    if isinstance(value, (int, float)):
        return [float(value)] * years
    if len(value) != years:
        raise ValueError(f"{name} has {len(value)} entries but hold period is {years} years")
    return [float(v) for v in value]


class DebtTranche(BaseModel):
    """One tranche of acquisition debt, in order of seniority."""

    name: str
    leverage_turns: float = Field(gt=0, description="Tranche size in turns of entry EBITDA")
    cash_rate: float = Field(ge=0, lt=1, description="Annual cash coupon, e.g. 0.055 for 5.5%")
    pik_rate: float = Field(default=0.0, ge=0, lt=1, description="Annual PIK rate accreting to principal")
    mandatory_amort_pct: float = Field(
        default=0.0, ge=0, le=1,
        description="Mandatory amortisation per year as a % of original principal (term-loan convention)",
    )
    sweepable: bool = Field(
        default=True,
        description="Whether excess cash sweeps against this tranche (bullet/mezz often not until seniors repay)",
    )


class RevolverAssumptions(BaseModel):
    """Revolving credit facility: drawn to cover shortfalls, repaid first."""

    commitment: float = Field(default=0.0, ge=0, description="Maximum facility size in currency")
    cash_rate: float = Field(default=0.0, ge=0, lt=1)
    undrawn_fee: float = Field(default=0.0, ge=0, lt=1, description="Commitment fee on the undrawn portion")


class DividendRecap(BaseModel):
    """A dividend recapitalisation: raise incremental debt, pay the proceeds out
    to the sponsor.

    This creates no enterprise value — it moves value forward in time and adds
    interest cost, which is precisely why it lifts IRR while leaving MOIC close
    to flat. Modelling it matters because it is one of the most common things a
    sponsor actually does, and a model without it systematically understates the
    returns of any deal that used one.

    Sizing is either a target leverage (the realistic instruction — "re-lever
    back to 4.5 turns and dividend the proceeds") or a fixed quantum.

    Convention: the recap is a **year-end** event. The incremental debt lands on
    the closing balance sheet of its year and begins accruing interest the
    following year, which is both economically right — the money existed for
    none of that year — and avoids introducing a second circularity into a
    within-year interest solve that is already iterative.
    """

    year: int = Field(ge=1, description="Projection year at whose end the recap occurs")
    target_leverage_turns: float | None = Field(
        default=None, gt=0,
        description="Re-lever total net debt to this multiple of the year's EBITDA",
    )
    amount: float | None = Field(
        default=None, gt=0, description="Or raise exactly this much incremental debt",
    )
    tranche: str | None = Field(
        default=None,
        description="Tranche the incremental debt joins; defaults to the most senior",
    )
    financing_fee_pct: float = Field(default=0.02, ge=0, lt=0.1)

    @model_validator(mode="after")
    def _exactly_one_sizing(self) -> "DividendRecap":
        if (self.target_leverage_turns is None) == (self.amount is None):
            raise ValueError(
                "a recap needs exactly one of target_leverage_turns or amount"
            )
        return self


class OperatingAssumptions(BaseModel):
    """The operating build. Scalars apply to every projection year."""

    entry_revenue: float = Field(gt=0)
    revenue_growth: float | list[float] = Field(description="Annual revenue growth, scalar or per-year")
    ebitda_margin: float | list[float] = Field(description="EBITDA margin on revenue, scalar or per-year")
    da_pct_revenue: float = Field(ge=0, lt=1, description="Depreciation & amortisation as % of revenue")
    capex_pct_revenue: float = Field(ge=0, lt=1)
    nwc_pct_revenue: float = Field(
        ge=0, lt=1,
        description="Net working capital as % of revenue; ΔNWC = this % × the change in revenue",
    )
    tax_rate: float = Field(ge=0, lt=1)


class Assumptions(BaseModel):
    """Full deal assumptions: entry, operations, structure, exit."""

    # Entry
    entry_ebitda: float = Field(gt=0)
    entry_multiple: float = Field(gt=0, description="Entry EV / EBITDA")
    # Operations
    operating: OperatingAssumptions
    # Capital structure
    tranches: list[DebtTranche] = Field(min_length=1, description="In order of seniority, most senior first")
    revolver: RevolverAssumptions = RevolverAssumptions()
    recaps: list[DividendRecap] = Field(
        default_factory=list,
        description="Dividend recapitalisations, at most one per projection year",
    )
    # Fees. Financing fees are capitalised at close and amortised straight-line
    # over the DEBT'S TENOR (ASC 835-30 convention), not the hold period.
    transaction_fee_pct_ev: float = Field(default=0.0, ge=0, lt=0.1, description="Advisory/legal fees as % of EV")
    financing_fee_pct_debt: float = Field(default=0.0, ge=0, lt=0.1, description="OID/arrangement fees as % of funded debt")
    financing_fee_tenor_years: int = Field(default=7, ge=1, le=10, description="Facility tenor over which financing fees amortise")
    exit_fee_pct_ev: float = Field(default=0.0, ge=0, lt=0.05, description="Sale-process costs at exit, % of exit EV, deducted from proceeds")
    # Tax attributes: losses carry forward and offset up to `nol_limit_pct` of a
    # later year's positive pre-tax income (80% is the post-TCJA US rule; set 0 to disable).
    nol_limit_pct: float = Field(default=0.8, ge=0, le=1)
    # The industry "circularity breaker". True = interest on the average of
    # opening and closing balances (correct, circular, solved iteratively).
    # False = interest on the opening balance only (approximate but acyclic) —
    # the toggle every bank model ships to stabilise a broken workbook.
    interest_on_average_balance: bool = Field(default=True)
    # Cash policy
    minimum_cash: float = Field(default=0.0, ge=0, description="Operating cash floor, funded in Uses at close")
    cash_sweep_pct: float = Field(default=1.0, ge=0, le=1, description="% of excess FCF applied to optional prepayment")
    # Exit
    hold_years: int = Field(ge=1, le=15)
    exit_multiple: float = Field(gt=0, description="Exit EV / EBITDA")

    @field_validator("tranches")
    @classmethod
    def _unique_names(cls, v: list[DebtTranche]) -> list[DebtTranche]:
        names = [t.name for t in v]
        if len(names) != len(set(names)):
            raise ValueError("tranche names must be unique")
        return v

    @model_validator(mode="after")
    def _validate_schedules(self) -> "Assumptions":
        # Fail fast on malformed per-year lists.
        _as_schedule(self.operating.revenue_growth, self.hold_years, "revenue_growth")
        _as_schedule(self.operating.ebitda_margin, self.hold_years, "ebitda_margin")
        return self

    @model_validator(mode="after")
    def _validate_recaps(self) -> "Assumptions":
        names = {t.name for t in self.tranches}
        years = [r.year for r in self.recaps]
        if len(years) != len(set(years)):
            raise ValueError("at most one dividend recap per year")
        for r in self.recaps:
            if r.year > self.hold_years:
                raise ValueError(
                    f"recap in year {r.year} but the hold is {self.hold_years} years"
                )
            if r.tranche is not None and r.tranche not in names:
                raise ValueError(f"recap names unknown tranche {r.tranche!r}")
        return self

    def recap_for(self, year: int) -> DividendRecap | None:
        return next((r for r in self.recaps if r.year == year), None)

    # Convenience accessors used by the engine
    def growth_schedule(self) -> list[float]:
        return _as_schedule(self.operating.revenue_growth, self.hold_years, "revenue_growth")

    def margin_schedule(self) -> list[float]:
        return _as_schedule(self.operating.ebitda_margin, self.hold_years, "ebitda_margin")

    @property
    def entry_ev(self) -> float:
        return self.entry_ebitda * self.entry_multiple

    @property
    def total_leverage_turns(self) -> float:
        return sum(t.leverage_turns for t in self.tranches)

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

from typing import Literal

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
    # The PIK toggle — the defining structural innovation of the 2006–07 credit
    # boom. The issuer may ELECT to stop paying cash interest and accrue it to
    # principal instead, at a step-up in rate. In 2007 roughly a fifth of buyout
    # firms used toggle debt and 13% of US junk-rated bond sales carried the
    # feature.
    #
    # This is distinct from `pik_rate`, which accrues unconditionally. A toggle
    # is an *option*, exercised only when cash is short — and it is the single
    # most important reason a real structure survives a year that a static model
    # says it should not.
    pik_toggle: bool = Field(
        default=False,
        description="Issuer may elect to PIK this tranche's cash coupon when cash is short",
    )
    pik_toggle_premium: float = Field(
        default=0.0075, ge=0, lt=0.1,
        description="Rate step-up when the toggle is elected (EFH's notes stepped ~75bps)",
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


class Divestiture(BaseModel):
    """A business sold during the hold, with the proceeds repaying debt.

    The mirror image of a recap: cash in rather than out, debt down rather than
    up. It matters because a large minority of buyouts are underwritten on a
    sum-of-the-parts — buy the whole, sell the pieces that do not fit, use the
    proceeds to delever — and a model without it will report that such a deal
    cannot service itself, which is true only of the half of the plan it can see.

    Deliberately proceeds-only. The *operating* effect of losing the divested
    business must be reflected in the revenue and margin path, because only the
    person building the case knows what was sold and what it earned. Modelling
    it any other way would mean guessing at a segment split the engine has no
    information about.

    Convention: a YEAR-END event, like a recap. Proceeds repay debt senior-first,
    and the reduced balance carries into the following year.

    Two consequences of that convention are worth stating, because both are
    conservative and neither is obvious:

    * The proceeds arrive *after* the year's liquidity test, so a business sold
      in January provides no relief at all to the year it was sold in. For a
      deal underwritten on a sum-of-the-parts this understates first-year
      headroom, and it is why such a deal can still break in year one here.
    * Interest that year is charged on the average of opening and the
      *pre*-disposal closing balance, so the schedule slightly overstates
      interest in a disposal year relative to the average-balance convention
      used everywhere else.

    Both are deliberate: modelling intra-year disposal timing would need a
    completion date the engine does not ask for, and guessing at one would
    trade a visible conservatism for an invisible assumption.
    """

    year: int = Field(ge=1, description="Projection year at whose end the sale completes")
    proceeds: float = Field(gt=0, description="Cash consideration received")
    fee_pct: float = Field(
        default=0.01, ge=0, lt=0.1, description="Sale-process costs, deducted from proceeds",
    )
    # Gain over tax basis, taxed at the deal's rate in the year of sale. Defaults
    # to zero rather than being inferred, because basis is deal-specific data the
    # engine has no way to know — but it is not ignorable: a multi-billion
    # disposal programme at a 35–38% rate is real cash, and a model that books
    # the proceeds and not the tax overstates the deleveraging.
    taxable_gain: float = Field(
        default=0.0, ge=0,
        description="Gain over tax basis, taxed at the operating tax rate in the sale year",
    )
    # Revenue that leaves with the business. Needed because working capital is
    # driven off the change in revenue: without it the model books a cash inflow
    # from "releasing" working capital that actually departed with the divested
    # unit and was already inside the sale consideration. On RJR that double
    # count was worth about 0.19x of MOIC, arriving in precisely the two years
    # the structure was trying to survive.
    revenue_removed: float = Field(
        default=0.0, ge=0,
        description="Revenue leaving with the business, excluded from the working-capital swing",
    )
    label: str = Field(default="Divestiture", description="What was sold")


class EquityInjection(BaseModel):
    """Follow-on sponsor capital put into the company mid-hold.

    The mirror of a recap in the other direction, and the mechanic without which
    a model calls every liquidity crisis a death. Real sponsors rescue good
    assets: Blackstone put fresh equity into Hilton alongside the 2010 debt
    restructuring, and KKR injected about $1.7bn into RJR in 1990 when the reset
    provisions on the PIK paper threatened a default. Both companies survived;
    a model with no injection mechanic reports both as failures.

    It is not free. The cash goes in at the START of the year — unlike a recap
    or a divestiture, which are year-end events — because rescue capital has to
    be available during the year it is rescuing. It then lands in the IRR vector
    as an outflow in that year and raises the invested-capital denominator, so
    a deal that needed rescuing shows a worse multiple than one that did not.
    That is the point: dilution is the cost of survival.
    """

    year: int = Field(ge=1, description="Projection year at whose start the capital goes in")
    amount: float = Field(ge=0, description="Cash injected by the sponsor")
    # Face value of debt extinguished alongside the injection. One field covers
    # all three shapes a real rescue takes, which is why there is no separate
    # restructuring mechanic:
    #   amount only                  -> a straight equity cure
    #   amount + larger debt_retired -> a repurchase below par, which is what
    #                                   Blackstone did in 2010, buying ~$2bn of
    #                                   Hilton's debt for ~$800m
    #   debt_retired with no amount  -> a debt-for-equity conversion
    # The difference between face retired and cash paid is a transfer from
    # creditors to equity: net debt falls by the face, so it lands in the
    # deleveraging line, and the identity closes without a separate term.
    debt_retired: float = Field(
        default=0.0, ge=0,
        description="Face value of debt extinguished, by repurchase below par or conversion",
    )
    # JUNIOR-first, and the distinction from a divestiture matters. Asset-sale
    # proceeds are a contractual mandatory prepayment, so they run senior-first
    # whether the issuer likes it or not. A discounted repurchase is the issuer
    # *choosing* what to buy, and it always buys the most discounted paper —
    # which is the junior end. Blackstone was not repurchasing money-good senior
    # CMBS at forty cents; the discount was in the mezzanine.
    retire_junior_first: bool = Field(
        default=True,
        description="Retire the junior end first (an elective repurchase) rather than senior-first",
    )
    label: str = Field(default="Follow-on equity", description="What the injection was for")

    @model_validator(mode="after")
    def _does_something(self) -> "EquityInjection":
        if self.amount <= 0 and self.debt_retired <= 0:
            raise ValueError("an injection must inject cash, retire debt, or both")
        return self


class InterestLimitation(BaseModel):
    """§163(j): the cap on how much business interest a company may deduct.

    The provision that binds hardest on a modern US LBO, and the reason the
    2017 Act changed sponsor structuring more than the rate cut did. A company
    may deduct business interest only up to 30% of adjusted taxable income.
    Above that the interest is still *paid* — it simply stops sheltering
    income, so cash tax is charged on money that went to lenders.

    Three details matter, and each one is a question worth being able to answer:

    * **The basis tightened in 2022.** For years beginning before 2022, ATI was
      an EBITDA-like measure; from 2022 it is EBIT-like, with no add-back for
      depreciation and amortisation. For a capital-intensive borrower that
      change alone cut the cap by a third or more. `ati_basis` carries it.
    * **Disallowed interest never expires.** Unlike an NOL it carries forward
      indefinitely, and is treated as business interest paid in the next year —
      so it competes with that year's own interest for the same capacity.
    * **Commitment fees are not interest.** The 2020 final regulations left
      undrawn revolver fees outside the definition, so they are deducted in
      full and excluded from the cap. Financing-fee amortisation *is* inside
      it: it is OID, which is interest.

    Disabled for any deal predating the 2017 Act. Before then §163(j) was an
    earnings-stripping rule aimed at related-party interest, which did not
    reach a third-party LBO — so applying today's cap to a 1988 or 2007 deal
    would be a straightforward anachronism.
    """

    enabled: bool = Field(
        default=True,
        description="Apply the cap. False for pre-2018 deals, or non-US borrowers.",
    )
    pct_of_ati: float = Field(
        default=0.30, ge=0, le=1,
        description="Share of adjusted taxable income deductible as interest (30% under current law)",
    )
    ati_basis: Literal["ebit", "ebitda"] = Field(
        default="ebit",
        description="EBIT-like ATI (current law) or EBITDA-like (years beginning before 2022)",
    )


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
    divestitures: list[Divestiture] = Field(
        default_factory=list,
        description="Businesses sold during the hold; proceeds repay debt senior-first",
    )
    injections: list[EquityInjection] = Field(
        default_factory=list,
        description="Follow-on sponsor capital; funds the year it is injected into",
    )
    # Fees. Financing fees are capitalised at close and amortised straight-line
    # over the DEBT'S TENOR (ASC 835-30 convention), not the hold period.
    transaction_fee_pct_ev: float = Field(default=0.0, ge=0, lt=0.1, description="Advisory/legal fees as % of EV")
    financing_fee_pct_debt: float = Field(default=0.0, ge=0, lt=0.1, description="OID/arrangement fees as % of funded debt")
    financing_fee_tenor_years: int = Field(default=7, ge=1, le=10, description="Facility tenor over which financing fees amortise")
    exit_fee_pct_ev: float = Field(default=0.0, ge=0, lt=0.05, description="Sale-process costs at exit, % of exit EV, deducted from proceeds")
    # Tax attributes: losses carry forward and offset up to `nol_limit_pct` of a
    # later year's positive pre-tax income.
    #
    # Read this carefully, because the natural misreading is expensive. The
    # parameter is the SHARE OF INCOME A CARRYFORWARD MAY SHELTER, not the size
    # of a restriction:
    #   1.0 = unlimited — a loss can shelter 100% of a later year (pre-TCJA US)
    #   0.8 = the post-TCJA §172(a) limitation
    #   0.0 = carryforwards can never be used at all
    # Setting 0.0 to mean "no limitation" produces a model that pays full cash
    # tax on income it believes is sheltered.
    nol_limit_pct: float = Field(
        default=0.8, ge=0, le=1,
        description="Share of a later year's pre-tax income a carryforward may shelter. "
                    "1.0 is unlimited (pre-TCJA); 0.8 is post-TCJA §172(a); 0.0 disables "
                    "the deduction entirely.",
    )
    # The §163(j) cap on interest deductibility. Enabled by default, because the
    # default deal here is a modern US LBO and a modern US LBO does not get full
    # relief on a six-turn structure. Every case study in the library predates
    # the 2017 Act and switches it off.
    interest_limitation: InterestLimitation = InterestLimitation()
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

    @model_validator(mode="after")
    def _validate_divestitures(self) -> "Assumptions":
        for d in self.divestitures:
            if d.year > self.hold_years:
                raise ValueError(
                    f"divestiture in year {d.year} but the hold is {self.hold_years} years"
                )
        for i in self.injections:
            if i.year > self.hold_years:
                raise ValueError(
                    f"equity injection in year {i.year} but the hold is "
                    f"{self.hold_years} years"
                )
        return self

    def recap_for(self, year: int) -> DividendRecap | None:
        return next((r for r in self.recaps if r.year == year), None)

    def divestitures_for(self, year: int) -> list[Divestiture]:
        return [d for d in self.divestitures if d.year == year]

    def injections_for(self, year: int) -> list[EquityInjection]:
        return [i for i in self.injections if i.year == year]

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

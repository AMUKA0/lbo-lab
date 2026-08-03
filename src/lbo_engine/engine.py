"""The core LBO engine.

For each projection year, in this order:
  1. Operating build: revenue → EBITDA → D&A → EBIT; capex; ΔNWC.
  2. Interest on each tranche and the revolver, computed on the AVERAGE of
     opening and closing balances. Closing balances depend on the cash sweep,
     which depends on interest — the classic circularity. Resolved by an
     iterative solve within the year (seed with interest on opening balances,
     recompute until the total interest charge stops moving), which is exactly
     what Excel's iterative-calculation mode does.
  3. Tax. Two limitations apply in order, because the order is the law's:
     §163(j) first caps the interest deduction at a share of adjusted taxable
     income, then §172(a) lets carryforwards shelter up to `nol_limit_pct` of
     what is left. Interest denied under the first is not lost — it carries
     forward indefinitely and competes with next year's interest for the same
     capacity. Tax is floored at zero and a loss carries forward as an NOL.
  4. Cash available for debt service:
       net income + D&A + financing-fee amortisation + PIK accrual (non-cash)
       − capex − ΔNWC + opening cash − minimum cash.
  5. Waterfall: mandatory amortisation (% of original principal) → revolver
     repayment → optional prepayment (cash sweep, senior-first, sweepable
     tranches only). Shortfalls draw the revolver.
  6. PIK interest accretes to the tranche balance (accrued on the opening
     balance, standard compounding convention).

  7. Dividend recapitalisation, if one falls in this year: incremental debt is
     raised against a named tranche and the proceeds, net of a financing fee,
     are paid out to the sponsor. Treated as a YEAR-END event — the money
     existed for none of that year, so it accrues no interest until the next
     one, and the within-year interest solve stays a single circularity rather
     than two.

At exit: exit EV = exit multiple × terminal EBITDA; equity = EV − net debt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lbo_engine.assumptions import Assumptions
from lbo_engine.sources_uses import SourcesAndUses, build_sources_and_uses

_MAX_ITERATIONS = 200
_TOLERANCE = 1e-10


def _rates(t, elected: frozenset[str]) -> tuple[float, float]:
    """Effective (cash, PIK) rates for a tranche given this year's elections.

    Electing the toggle moves the whole cash coupon into PIK and steps the rate
    up — the lender is compensated for waiting. Any unconditional `pik_rate`
    keeps accruing alongside.
    """
    if t.name in elected:
        return 0.0, t.pik_rate + t.cash_rate + t.pik_toggle_premium
    return t.cash_rate, t.pik_rate


@dataclass
class TrancheYear:
    opening: float
    cash_interest: float
    pik_accrual: float
    mandatory_repayment: float
    sweep_repayment: float
    closing: float
    # True where the issuer elected the PIK toggle this year rather than paying
    # cash interest it did not have.
    pik_elected: bool = False


@dataclass
class YearRow:
    year: int
    revenue: float
    ebitda: float
    da: float
    ebit: float
    capex: float
    delta_nwc: float
    fee_amortisation: float
    cash_interest_total: float
    pik_accrual_total: float
    revolver_undrawn_fee: float
    ebt: float
    # §163(j). `business_interest` is what the section reaches — cash coupon,
    # PIK accrual and fee amortisation, but not the undrawn commitment fee.
    # `deducted` is what tax relief was actually given on; the gap is the cost
    # of the cap, and it shows up as tax paid on money that went to lenders.
    business_interest: float
    interest_capacity: float
    interest_deducted: float
    interest_cf_opening: float
    interest_cf_closing: float
    # What tax is charged on, before NOLs. Differs from `ebt` by exactly the
    # interest the cap disallowed.
    taxable_income: float
    nol_opening: float
    nol_used: float
    nol_closing: float
    taxes: float
    net_income: float
    cash_available_for_debt_service: float
    revolver_opening: float
    revolver_draw: float
    revolver_repayment: float
    revolver_closing: float
    opening_cash: float
    closing_cash: float
    # Tranches on which the PIK toggle was elected this year, junior-first. A
    # non-empty list means the structure could not pay cash interest out of
    # operations and exercised an option rather than breaking.
    pik_elections: list[str] = field(default_factory=list)
    # Dividend recap, if one falls in this year. `raised` is the gross
    # incremental debt; `dividend` is what reaches the sponsor after the
    # financing fee. A target that would require *repaying* debt rather than
    # raising it leaves `raised` at zero — reported rather than silently
    # rounded away, so the UI can say the recap was not fundable.
    # Divestiture proceeds applied to debt this year, and the sale costs paid.
    # Follow-on sponsor capital injected at the START of this year.
    equity_injected: float = 0.0
    debt_retired: float = 0.0
    injection_labels: list[str] = field(default_factory=list)
    divestiture_proceeds: float = 0.0
    divestiture_fees: float = 0.0
    divestiture_tax: float = 0.0
    divestiture_labels: list[str] = field(default_factory=list)
    recap_target: float = 0.0
    recap_raised: float = 0.0
    recap_fee: float = 0.0
    recap_dividend: float = 0.0
    tranches: dict[str, TrancheYear] = field(default_factory=dict)
    interest_iterations: int = 0

    @property
    def total_debt_closing(self) -> float:
        return self.revolver_closing + sum(t.closing for t in self.tranches.values())


@dataclass
class LBOResult:
    assumptions: Assumptions
    sources_uses: SourcesAndUses
    years: list[YearRow]
    exit_ebitda: float
    exit_ev: float
    exit_net_debt: float
    exit_fees: float
    exit_equity: float

    @property
    def entry_equity(self) -> float:
        return self.sources_uses.sponsor_equity

    @property
    def entry_net_debt(self) -> float:
        return self.sources_uses.total_debt - self.sources_uses.cash_to_balance_sheet

    @property
    def total_injected(self) -> float:
        """Follow-on capital the sponsor had to put in after close."""
        return sum(y.equity_injected for y in self.years)

    @property
    def total_invested(self) -> float:
        """Every dollar the sponsor put in: the cheque at close plus any rescue
        capital. This is the denominator a multiple should be struck on — a deal
        that needed rescuing did not return its money on the original cheque."""
        return self.entry_equity + self.total_injected

    @property
    def dividends(self) -> list[float]:
        """Recap proceeds reaching the sponsor, by year."""
        return [y.recap_dividend for y in self.years]

    @property
    def total_dividends(self) -> float:
        return sum(self.dividends)

    @property
    def moic(self) -> float:
        """On TOTAL proceeds — recap dividends plus exit equity.

        A recap that returned half the cheque in year three is capital the
        sponsor genuinely has back; excluding it would understate the multiple
        on every deal that used one.
        """
        return (self.total_dividends + self.exit_equity) / self.total_invested

    @property
    def equity_cash_flows(self) -> list[float]:
        """Sponsor cash flows: cheque out at close, recap dividends in the years
        they are paid, exit proceeds at the end.

        The interim flows are the whole point of a recap — the same total
        returned earlier is a materially higher IRR.
        """
        flows = [-self.entry_equity] + [0.0] * self.assumptions.hold_years
        for y in self.years:
            # A recap is a year-END event, so it lands at index `year`. An
            # injection funds the year it goes into and is spent at its START,
            # which is index `year - 1` — discounting it a year later than it
            # was actually paid understates its cost and flatters IRR.
            flows[y.year] += y.recap_dividend
            flows[y.year - 1] -= y.equity_injected
        flows[-1] += self.exit_equity
        return flows

    def to_dataframe(self):
        """Annual schedule as a pandas DataFrame, one row per projection year."""
        import pandas as pd

        records = []
        for y in self.years:
            rec = {
                "year": y.year,
                "revenue": y.revenue,
                "ebitda": y.ebitda,
                "d&a": y.da,
                "ebit": y.ebit,
                "capex": y.capex,
                "delta_nwc": y.delta_nwc,
                "cash_interest": y.cash_interest_total,
                "pik_accrual": y.pik_accrual_total,
                "nol_closing": y.nol_closing,
                "taxes": y.taxes,
                "net_income": y.net_income,
                "cads": y.cash_available_for_debt_service,
                "revolver_closing": y.revolver_closing,
                "closing_cash": y.closing_cash,
                "recap_debt_raised": y.recap_raised,
                "recap_dividend": y.recap_dividend,
                "total_debt": y.total_debt_closing,
            }
            for name, t in y.tranches.items():
                rec[f"{name}_closing"] = t.closing
            records.append(rec)
        return pd.DataFrame.from_records(records).set_index("year")


def run_lbo(a: Assumptions) -> LBOResult:
    su = build_sources_and_uses(a)

    growth = a.growth_schedule()
    margin = a.margin_schedule()
    # Straight-line over the facility tenor (ASC 835-30); any portion beyond the
    # hold simply never hits the P&L before exit.
    fee_amort = su.financing_fees / a.financing_fee_tenor_years

    tranche_original = dict(su.tranche_amounts)
    tranche_opening = dict(su.tranche_amounts)
    revolver_opening = 0.0
    opening_cash = su.cash_to_balance_sheet
    nol_opening = 0.0
    # Interest §163(j) denied in earlier years, treated as paid again this one.
    interest_cf_opening = 0.0
    prev_revenue = a.operating.entry_revenue
    # Revenue that left with a business sold at the end of the previous year.
    # The resulting fall in revenue is inorganic, so it must not drive a working
    # capital release — that cash went with the business.
    inorganic_decline = 0.0

    years: list[YearRow] = []
    for i in range(a.hold_years):
        year_no = i + 1
        revenue = prev_revenue * (1.0 + growth[i])
        ebitda = revenue * margin[i]
        da = a.operating.da_pct_revenue * revenue
        ebit = ebitda - da
        capex = a.operating.capex_pct_revenue * revenue
        organic_change = (revenue - prev_revenue) + inorganic_decline
        delta_nwc = a.operating.nwc_pct_revenue * organic_change

        # Follow-on equity funds the year it goes into, so it lands in opening
        # cash before the waterfall rather than at year end like the other two
        # capital events. Rescue capital that arrived after the crisis would not
        # be rescuing anything.
        injections = a.injections_for(year_no)
        injected = sum(i.amount for i in injections)
        retired = sum(i.debt_retired for i in injections)
        opening_cash += injected
        # Debt extinguished at the start of the year, senior-first, so the year
        # is solved against the post-restructuring balance sheet. Retiring it at
        # year end would leave the company paying a full year of interest on
        # paper it no longer owes.
        if retired > 0:
            remaining = retired
            junior_first = all(i.retire_junior_first for i in injections if i.debt_retired > 0)
            order = list(reversed(a.tranches)) if junior_first else list(a.tranches)
            for t in order:
                if remaining <= 0:
                    break
                pay = min(remaining, tranche_opening[t.name])
                tranche_opening[t.name] -= pay
                remaining -= pay
            # The revolver is the most senior claim, so it is repaid last on an
            # elective repurchase and first on a mandatory one.
            if remaining > 0:
                repay = min(revolver_opening, remaining)
                revolver_opening -= repay
                remaining -= repay

        row = _solve_year(
            a, year_no, revenue, ebitda, da, ebit, capex, delta_nwc, fee_amort,
            tranche_original, tranche_opening, revolver_opening, opening_cash,
            nol_opening, interest_cf_opening,
        )
        row.equity_injected = injected
        row.debt_retired = retired
        row.injection_labels = [i.label for i in injections]

        # Year-end divestitures, applied before any recap: proceeds pay down debt,
        # which is what a sum-of-the-parts underwriting actually relies on.
        inorganic_decline = 0.0
        for sale in a.divestitures_for(year_no):
            _apply_divestiture(a, sale, row)
            inorganic_decline += sale.revenue_removed

        # Year-end dividend recapitalisation, applied after the year is solved so
        # the new debt accrues no interest until the following year.
        recap = a.recap_for(year_no)
        if recap is not None:
            fee_amort += (
                _apply_recap(a, recap, row, ebitda, tranche_original)
                / a.financing_fee_tenor_years
            )

        years.append(row)

        tranche_opening = {name: t.closing for name, t in row.tranches.items()}
        revolver_opening = row.revolver_closing
        opening_cash = row.closing_cash
        nol_opening = row.nol_closing
        interest_cf_opening = row.interest_cf_closing
        prev_revenue = revenue

    exit_ebitda = years[-1].ebitda
    exit_ev = a.exit_multiple * exit_ebitda
    exit_net_debt = years[-1].total_debt_closing - years[-1].closing_cash
    exit_fees = a.exit_fee_pct_ev * exit_ev
    exit_equity = exit_ev - exit_net_debt - exit_fees
    if exit_equity < 0:
        exit_equity = 0.0  # sponsor equity cannot go below zero (limited liability)

    return LBOResult(
        assumptions=a,
        sources_uses=su,
        years=years,
        exit_ebitda=exit_ebitda,
        exit_ev=exit_ev,
        exit_net_debt=exit_net_debt,
        exit_fees=exit_fees,
        exit_equity=exit_equity,
    )


def _apply_divestiture(a: Assumptions, sale, row: YearRow) -> None:
    """Apply sale proceeds to the debt stack, senior-first.

    Senior-first because that is what a credit agreement requires: asset-sale
    proceeds are a mandatory prepayment, and the mandatory-prepayment waterfall
    runs top down. Anything left once every tranche is repaid stays as cash.

    Tax on the gain is paid out of the proceeds before any of it reaches the
    lenders — booking the cash and not the tax would overstate the deleveraging.
    """
    gain_tax = sale.taxable_gain * a.operating.tax_rate
    row.divestiture_tax += gain_tax
    net = sale.proceeds - sale.fee_pct * sale.proceeds - gain_tax
    row.divestiture_proceeds += net
    row.divestiture_fees += sale.fee_pct * sale.proceeds
    row.divestiture_labels.append(sale.label)

    remaining = net
    # The revolver is the most senior claim and is repaid ahead of the tranches.
    repay = min(row.revolver_closing, remaining)
    row.revolver_closing -= repay
    remaining -= repay
    for t in a.tranches:
        if remaining <= 0:
            break
        pay = min(remaining, row.tranches[t.name].closing)
        row.tranches[t.name].closing -= pay
        remaining -= pay
    # Surplus beyond the whole capital structure simply sits on the balance sheet.
    row.closing_cash += remaining


def _apply_recap(
    a: Assumptions, recap, row: YearRow, ebitda: float, tranche_original: dict[str, float]
) -> float:
    """Raise incremental debt at year end and dividend the net proceeds out.

    Mutates `row` in place and returns the financing fee, which the caller adds
    to the amortising pool (ASC 835-30 again — the fee on new debt amortises
    over the facility tenor like any other, it does not hit the P&L at once).

    Sizing by target leverage is the instruction a sponsor actually gives:
    re-lever to N turns and take out whatever that raises. If the company is
    already below the target — or the target is above where it already sits —
    the recap raises nothing, and that is recorded rather than hidden.
    """
    net_debt = row.total_debt_closing - row.closing_cash
    if recap.amount is not None:
        target = recap.amount
        raised = recap.amount
    else:
        target = recap.target_leverage_turns * ebitda
        # Only the *incremental* debt is raised; a target below current leverage
        # would mean repaying, which is not a recap.
        raised = max(target - net_debt, 0.0)

    row.recap_target = target
    if raised <= 0.0:
        return 0.0

    name = recap.tranche or a.tranches[0].name
    row.tranches[name].closing += raised
    # Mandatory amortisation is a % of ORIGINAL principal, so incremental debt
    # has to join that base or it would never amortise again.
    tranche_original[name] += raised

    fee = recap.financing_fee_pct * raised
    row.recap_raised = raised
    row.recap_fee = fee
    row.recap_dividend = raised - fee
    return fee


def _solve_year(
    a: Assumptions,
    year_no: int,
    revenue: float,
    ebitda: float,
    da: float,
    ebit: float,
    capex: float,
    delta_nwc: float,
    fee_amort: float,
    tranche_original: dict[str, float],
    tranche_opening: dict[str, float],
    revolver_opening: float,
    opening_cash: float,
    nol_opening: float,
    interest_cf_opening: float,
) -> YearRow:
    """Resolve one year, electing the PIK toggle only if the year cannot be paid.

    The election is a *last resort*, searched junior-first: try paying everything
    in cash; if that breaks the structure, toggle the most junior eligible
    tranche and try again; then the next one up. This mirrors how the option is
    actually used — nobody PIKs a coupon they can afford, because it steps the
    rate up and compounds — and it means a toggle only ever appears in the
    schedule at the exact moment it was needed.

    Each attempt re-runs the full iterative interest solve, because changing a
    coupon changes the circularity it sits inside.
    """
    eligible = [t.name for t in a.tranches if t.pik_toggle]
    failure: ValueError | None = None
    # 0 elections, then 1 (most junior), then 2, ... — the cheapest fix first.
    for depth in range(len(eligible) + 1):
        elected = frozenset(eligible[::-1][:depth])
        try:
            row = _solve_year_with(
                a, year_no, revenue, ebitda, da, ebit, capex, delta_nwc, fee_amort,
                tranche_original, tranche_opening, revolver_opening, opening_cash,
                nol_opening, interest_cf_opening, elected,
            )
        except ValueError as exc:
            failure = exc
            continue
        row.pik_elections = [n for n in eligible if n in elected]
        for name in elected:
            row.tranches[name].pik_elected = True
        return row

    assert failure is not None
    raise failure


def _solve_year_with(
    a: Assumptions,
    year_no: int,
    revenue: float,
    ebitda: float,
    da: float,
    ebit: float,
    capex: float,
    delta_nwc: float,
    fee_amort: float,
    tranche_original: dict[str, float],
    tranche_opening: dict[str, float],
    revolver_opening: float,
    opening_cash: float,
    nol_opening: float,
    interest_cf_opening: float,
    elected: frozenset[str],
) -> YearRow:
    """Iteratively resolve the interest ↔ debt-balance circularity for one year,
    given a fixed set of toggle elections."""
    # Seed: interest on opening balances (first pass of the iterative calc).
    cash_interest = {
        t.name: _rates(t, elected)[0] * tranche_opening[t.name] for t in a.tranches
    }
    revolver_interest = a.revolver.cash_rate * revolver_opening

    if not a.interest_on_average_balance:
        # Circularity breaker: interest on opening balances only. Acyclic, so
        # a single pass is the exact answer under that convention.
        row = _build_year(
            a, year_no, revenue, ebitda, da, ebit, capex, delta_nwc, fee_amort,
            tranche_original, tranche_opening, revolver_opening, opening_cash,
            nol_opening, interest_cf_opening, cash_interest, revolver_interest,
            elected,
        )
        row.interest_iterations = 1
        return row

    row: YearRow | None = None
    prev_total_interest = float("inf")
    for iteration in range(1, _MAX_ITERATIONS + 1):
        row = _build_year(
            a, year_no, revenue, ebitda, da, ebit, capex, delta_nwc, fee_amort,
            tranche_original, tranche_opening, revolver_opening, opening_cash,
            nol_opening, interest_cf_opening, cash_interest, revolver_interest,
            elected,
        )
        # Recompute interest on average balances given the resulting closings.
        cash_interest = {
            t.name: _rates(t, elected)[0]
            * 0.5
            * (tranche_opening[t.name] + row.tranches[t.name].closing)
            for t in a.tranches
        }
        revolver_interest = a.revolver.cash_rate * 0.5 * (revolver_opening + row.revolver_closing)

        total = sum(cash_interest.values()) + revolver_interest
        if abs(total - prev_total_interest) < _TOLERANCE:
            row.interest_iterations = iteration
            break
        prev_total_interest = total
    else:
        raise RuntimeError(f"Interest solve failed to converge in year {year_no}")

    assert row is not None
    return row


def _build_year(
    a: Assumptions,
    year_no: int,
    revenue: float,
    ebitda: float,
    da: float,
    ebit: float,
    capex: float,
    delta_nwc: float,
    fee_amort: float,
    tranche_original: dict[str, float],
    tranche_opening: dict[str, float],
    revolver_opening: float,
    opening_cash: float,
    nol_opening: float,
    interest_cf_opening: float,
    cash_interest: dict[str, float],
    revolver_interest: float,
    elected: frozenset[str] = frozenset(),
) -> YearRow:
    """One pass of the year's income statement, cash flow and debt waterfall
    for a GIVEN interest charge and set of toggle elections."""
    pik_accrual = {
        t.name: _rates(t, elected)[1] * tranche_opening[t.name] for t in a.tranches
    }
    undrawn = max(a.revolver.commitment - revolver_opening, 0.0)
    undrawn_fee = a.revolver.undrawn_fee * undrawn

    cash_interest_total = sum(cash_interest.values()) + revolver_interest
    pik_total = sum(pik_accrual.values())

    # Income statement. Financing-fee amortisation and PIK are expenses of the
    # period whether or not tax allows them this year.
    ebt = ebit - cash_interest_total - pik_total - fee_amort - undrawn_fee

    # --- §163(j): cap the interest DEDUCTION, not the interest ---------------
    # Fee amortisation is inside the cap because it is OID, which is interest.
    # The undrawn commitment fee is outside it: the 2020 final regulations left
    # commitment fees out of the definition, so they are deducted in full.
    business_interest = cash_interest_total + pik_total + fee_amort
    subject = business_interest + interest_cf_opening
    lim = a.interest_limitation
    if lim.enabled:
        # ATI is struck before interest and before any NOL. The EBITDA basis
        # applied to years beginning before 2022; EBIT is current law.
        ati = ebit - undrawn_fee + (da if lim.ati_basis == "ebitda" else 0.0)
        interest_capacity = lim.pct_of_ati * max(ati, 0.0)
        interest_deducted = min(subject, interest_capacity)
    else:
        # No cap: everything is deducted, and the reported capacity is the
        # deduction itself rather than an infinity nothing can display.
        interest_deducted = subject
        interest_capacity = subject
    # Denied interest carries forward indefinitely — no expiry, unlike an NOL.
    interest_cf_closing = subject - interest_deducted

    # Tax base: book EBT, plus back the interest tax would not allow.
    taxable_income = ebt + (business_interest - interest_deducted)

    if taxable_income > 0:
        # NOLs shelter up to nol_limit_pct of positive taxable income (§172(a)).
        nol_used = min(nol_opening, a.nol_limit_pct * taxable_income)
        taxes = (taxable_income - nol_used) * a.operating.tax_rate
        nol_closing = nol_opening - nol_used
    else:
        nol_used = 0.0
        taxes = 0.0
        nol_closing = nol_opening - taxable_income  # the loss carries forward
    # The disallowed interest was still paid, so it still reduces net income —
    # it is the tax charge above it that the cap raises.
    net_income = ebt - taxes

    # Cash flow: add back non-cash charges (D&A, fee amortisation, PIK).
    cfads = net_income + da + fee_amort + pik_total - capex - delta_nwc
    cash_available = opening_cash + cfads - a.minimum_cash

    # --- Debt waterfall ---
    # 1. Mandatory amortisation: % of ORIGINAL principal, capped at what's outstanding
    #    (opening + this year's PIK accretion).
    balances = {name: tranche_opening[name] + pik_accrual[name] for name in tranche_opening}
    mandatory: dict[str, float] = {}
    for t in a.tranches:
        m = min(t.mandatory_amort_pct * tranche_original[t.name], balances[t.name])
        mandatory[t.name] = m
        balances[t.name] -= m
    cash_after_mandatory = cash_available - sum(mandatory.values())

    revolver_draw = 0.0
    revolver_repayment = 0.0
    sweep: dict[str, float] = {t.name: 0.0 for t in a.tranches}

    if cash_after_mandatory < 0:
        # Shortfall: mandatory payments are contractual; the revolver funds the gap.
        revolver_draw = -cash_after_mandatory
        if revolver_draw > a.revolver.commitment - revolver_opening + 1e-9:
            raise ValueError(
                f"Year {year_no}: cash shortfall of {revolver_draw:,.1f} exceeds "
                f"undrawn revolver capacity — the structure fails. "
                "Reduce leverage, add revolver commitment, or revisit operating assumptions."
            )
        closing_cash = a.minimum_cash
    else:
        # 2. Repay the revolver first (it is the most senior, and prepayable at will).
        revolver_repayment = min(revolver_opening, cash_after_mandatory)
        remaining = cash_after_mandatory - revolver_repayment
        # 3. Cash sweep: the sweep % of remaining excess cash, applied senior-first
        #    to sweepable tranches.
        sweep_pool = a.cash_sweep_pct * remaining
        for t in a.tranches:
            if not t.sweepable or sweep_pool <= 0:
                continue
            pay = min(sweep_pool, balances[t.name])
            sweep[t.name] = pay
            balances[t.name] -= pay
            sweep_pool -= pay
        swept = sum(sweep.values())
        closing_cash = a.minimum_cash + (remaining - swept)

    revolver_closing = revolver_opening + revolver_draw - revolver_repayment

    tranches = {
        t.name: TrancheYear(
            opening=tranche_opening[t.name],
            cash_interest=cash_interest[t.name],
            pik_accrual=pik_accrual[t.name],
            mandatory_repayment=mandatory[t.name],
            sweep_repayment=sweep[t.name],
            closing=balances[t.name],
        )
        for t in a.tranches
    }

    return YearRow(
        year=year_no,
        revenue=revenue,
        ebitda=ebitda,
        da=da,
        ebit=ebit,
        capex=capex,
        delta_nwc=delta_nwc,
        fee_amortisation=fee_amort,
        cash_interest_total=cash_interest_total,
        pik_accrual_total=pik_total,
        revolver_undrawn_fee=undrawn_fee,
        ebt=ebt,
        business_interest=business_interest,
        interest_capacity=interest_capacity,
        interest_deducted=interest_deducted,
        interest_cf_opening=interest_cf_opening,
        interest_cf_closing=interest_cf_closing,
        taxable_income=taxable_income,
        nol_opening=nol_opening,
        nol_used=nol_used,
        nol_closing=nol_closing,
        taxes=taxes,
        net_income=net_income,
        cash_available_for_debt_service=cfads,
        revolver_opening=revolver_opening,
        revolver_draw=revolver_draw,
        revolver_repayment=revolver_repayment,
        revolver_closing=revolver_closing,
        opening_cash=opening_cash,
        closing_cash=closing_cash,
        tranches=tranches,
    )

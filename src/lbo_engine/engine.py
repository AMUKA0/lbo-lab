"""The core LBO engine.

For each projection year, in this order:
  1. Operating build: revenue → EBITDA → D&A → EBIT; capex; ΔNWC.
  2. Interest on each tranche and the revolver, computed on the AVERAGE of
     opening and closing balances. Closing balances depend on the cash sweep,
     which depends on interest — the classic circularity. Resolved by an
     iterative solve within the year (seed with interest on opening balances,
     recompute until the total interest charge stops moving), which is exactly
     what Excel's iterative-calculation mode does.
  3. Tax on EBT, floored at zero (losses do not generate cash refunds;
     NOL carryforwards are a documented simplification — see README).
  4. Cash available for debt service:
       net income + D&A + financing-fee amortisation + PIK accrual (non-cash)
       − capex − ΔNWC + opening cash − minimum cash.
  5. Waterfall: mandatory amortisation (% of original principal) → revolver
     repayment → optional prepayment (cash sweep, senior-first, sweepable
     tranches only). Shortfalls draw the revolver.
  6. PIK interest accretes to the tranche balance (accrued on the opening
     balance, standard compounding convention).

At exit: exit EV = exit multiple × terminal EBITDA; equity = EV − net debt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lbo_engine.assumptions import Assumptions
from lbo_engine.sources_uses import SourcesAndUses, build_sources_and_uses

_MAX_ITERATIONS = 200
_TOLERANCE = 1e-10


@dataclass
class TrancheYear:
    opening: float
    cash_interest: float
    pik_accrual: float
    mandatory_repayment: float
    sweep_repayment: float
    closing: float


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
    taxes: float
    net_income: float
    cash_available_for_debt_service: float
    revolver_opening: float
    revolver_draw: float
    revolver_repayment: float
    revolver_closing: float
    opening_cash: float
    closing_cash: float
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
    exit_equity: float

    @property
    def entry_equity(self) -> float:
        return self.sources_uses.sponsor_equity

    @property
    def entry_net_debt(self) -> float:
        return self.sources_uses.total_debt - self.sources_uses.cash_to_balance_sheet

    @property
    def moic(self) -> float:
        return self.exit_equity / self.entry_equity

    @property
    def equity_cash_flows(self) -> list[float]:
        """Sponsor cash flows: cheque out at close, proceeds at exit, nothing between.

        (Dividend recaps would add interim flows; not modelled in v1.)
        """
        flows = [-self.entry_equity] + [0.0] * self.assumptions.hold_years
        flows[-1] = self.exit_equity
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
                "taxes": y.taxes,
                "net_income": y.net_income,
                "cads": y.cash_available_for_debt_service,
                "revolver_closing": y.revolver_closing,
                "closing_cash": y.closing_cash,
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
    fee_amort = su.financing_fees / a.hold_years  # straight-line over the hold

    tranche_original = dict(su.tranche_amounts)
    tranche_opening = dict(su.tranche_amounts)
    revolver_opening = 0.0
    opening_cash = su.cash_to_balance_sheet
    prev_revenue = a.operating.entry_revenue

    years: list[YearRow] = []
    for i in range(a.hold_years):
        year_no = i + 1
        revenue = prev_revenue * (1.0 + growth[i])
        ebitda = revenue * margin[i]
        da = a.operating.da_pct_revenue * revenue
        ebit = ebitda - da
        capex = a.operating.capex_pct_revenue * revenue
        delta_nwc = a.operating.nwc_pct_revenue * (revenue - prev_revenue)

        row = _solve_year(
            a, year_no, revenue, ebitda, da, ebit, capex, delta_nwc, fee_amort,
            tranche_original, tranche_opening, revolver_opening, opening_cash,
        )
        years.append(row)

        tranche_opening = {name: t.closing for name, t in row.tranches.items()}
        revolver_opening = row.revolver_closing
        opening_cash = row.closing_cash
        prev_revenue = revenue

    exit_ebitda = years[-1].ebitda
    exit_ev = a.exit_multiple * exit_ebitda
    exit_net_debt = years[-1].total_debt_closing - years[-1].closing_cash
    exit_equity = exit_ev - exit_net_debt
    if exit_equity < 0:
        exit_equity = 0.0  # sponsor equity cannot go below zero (limited liability)

    return LBOResult(
        assumptions=a,
        sources_uses=su,
        years=years,
        exit_ebitda=exit_ebitda,
        exit_ev=exit_ev,
        exit_net_debt=exit_net_debt,
        exit_equity=exit_equity,
    )


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
) -> YearRow:
    """Iteratively resolve the interest ↔ debt-balance circularity for one year."""
    # Seed: interest on opening balances (first pass of the iterative calc).
    cash_interest = {t.name: t.cash_rate * tranche_opening[t.name] for t in a.tranches}
    revolver_interest = a.revolver.cash_rate * revolver_opening

    row: YearRow | None = None
    prev_total_interest = float("inf")
    for iteration in range(1, _MAX_ITERATIONS + 1):
        row = _build_year(
            a, year_no, revenue, ebitda, da, ebit, capex, delta_nwc, fee_amort,
            tranche_original, tranche_opening, revolver_opening, opening_cash,
            cash_interest, revolver_interest,
        )
        # Recompute interest on average balances given the resulting closings.
        cash_interest = {
            t.name: t.cash_rate * 0.5 * (tranche_opening[t.name] + row.tranches[t.name].closing)
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
    cash_interest: dict[str, float],
    revolver_interest: float,
) -> YearRow:
    """One pass of the year's income statement, cash flow and debt waterfall
    for a GIVEN interest charge."""
    pik_accrual = {t.name: t.pik_rate * tranche_opening[t.name] for t in a.tranches}
    undrawn = max(a.revolver.commitment - revolver_opening, 0.0)
    undrawn_fee = a.revolver.undrawn_fee * undrawn

    cash_interest_total = sum(cash_interest.values()) + revolver_interest
    pik_total = sum(pik_accrual.values())

    # Income statement. Financing-fee amortisation and PIK are tax-deductible.
    ebt = ebit - cash_interest_total - pik_total - fee_amort - undrawn_fee
    taxes = max(ebt, 0.0) * a.operating.tax_rate
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

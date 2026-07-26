"""Sources & Uses at close.

Cash-free / debt-free convention:
  Uses    = purchase of the enterprise (entry EV)
          + transaction fees (advisory, legal — expensed to equity at close)
          + financing fees (OID / arrangement — capitalised, amortised over the hold)
          + cash funded to the balance sheet (the minimum operating cash)
  Sources = each debt tranche (turns × entry EBITDA)
          + sponsor equity (the plug: Uses − total debt)

Sponsor equity as the plug is the standard construction: debt capacity is set
by the market (leverage multiples), and equity fills whatever remains.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lbo_engine.assumptions import Assumptions


@dataclass(frozen=True)
class SourcesAndUses:
    entry_ev: float
    transaction_fees: float
    financing_fees: float
    cash_to_balance_sheet: float
    tranche_amounts: dict[str, float] = field(default_factory=dict)
    total_debt: float = 0.0
    sponsor_equity: float = 0.0

    @property
    def total_uses(self) -> float:
        return self.entry_ev + self.transaction_fees + self.financing_fees + self.cash_to_balance_sheet

    @property
    def total_sources(self) -> float:
        return self.total_debt + self.sponsor_equity


def build_sources_and_uses(a: Assumptions) -> SourcesAndUses:
    entry_ev = a.entry_ev
    tranche_amounts = {t.name: t.leverage_turns * a.entry_ebitda for t in a.tranches}
    total_debt = sum(tranche_amounts.values())

    transaction_fees = a.transaction_fee_pct_ev * entry_ev
    financing_fees = a.financing_fee_pct_debt * total_debt
    cash_to_bs = a.minimum_cash

    uses = entry_ev + transaction_fees + financing_fees + cash_to_bs
    sponsor_equity = uses - total_debt
    if sponsor_equity <= 0:
        raise ValueError(
            f"Debt ({total_debt:,.1f}) covers all uses ({uses:,.1f}); "
            "no equity cheque required — leverage assumptions are implausible."
        )

    return SourcesAndUses(
        entry_ev=entry_ev,
        transaction_fees=transaction_fees,
        financing_fees=financing_fees,
        cash_to_balance_sheet=cash_to_bs,
        tranche_amounts=tranche_amounts,
        total_debt=total_debt,
        sponsor_equity=sponsor_equity,
    )

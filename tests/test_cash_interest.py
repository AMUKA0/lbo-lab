"""Interest earned on balance-sheet cash.

Trivial arithmetic, easy to get subtly wrong in three places: the balance it is
struck on, whether it is inside the interest circularity, and what §163(j) does
with it. These pin all three.
"""

import pytest

from lbo_engine import InterestLimitation, run_lbo
from lbo_engine.returns import sponsor_irr


def _hoarder(deal, rate: float = 0.04):
    """A deal that keeps its cash rather than sweeping it — otherwise there is
    no balance to earn on and the feature is untestable."""
    d = deal.model_copy(deep=True)
    d.cash_sweep_pct = 0.0
    d.cash_deposit_rate = rate
    return d


class TestTheBalanceItIsStruckOn:
    def test_average_of_opening_and_closing(self, rich_deal):
        d = _hoarder(rich_deal)
        for y in run_lbo(d).years:
            assert y.interest_income == pytest.approx(
                d.cash_deposit_rate * 0.5 * (y.opening_cash + y.closing_cash), abs=1e-6
            )

    def test_opening_only_under_the_circularity_breaker(self, rich_deal):
        """The same convention the debt uses, so the two cannot disagree about
        what 'average' means."""
        d = _hoarder(rich_deal)
        d.interest_on_average_balance = False
        for y in run_lbo(d).years:
            assert y.interest_income == pytest.approx(
                d.cash_deposit_rate * y.opening_cash, abs=1e-9
            )

    def test_a_deal_that_sweeps_everything_earns_almost_nothing(self, rich_deal):
        """Not zero — the minimum cash balance still sits on deposit. The point
        is that the feature cannot flatter a fully swept structure."""
        d = rich_deal.model_copy(deep=True)
        d.cash_deposit_rate = 0.04
        d.cash_sweep_pct = 1.0
        swept = run_lbo(d)
        hoarded = run_lbo(_hoarder(rich_deal))
        assert sum(y.interest_income for y in swept.years) < 0.25 * sum(
            y.interest_income for y in hoarded.years)


class TestItIsInsideTheCircularity:
    def test_income_compounds_into_the_balance_it_is_earned_on(self, rich_deal):
        """Income raises cash, which raises income — the same fixed point the
        debt sits in, not a second solve bolted on afterwards. If it were struck
        outside the loop, closing cash would be short by the income itself."""
        d = _hoarder(rich_deal)
        r = run_lbo(d)
        for prev, nxt in zip(r.years, r.years[1:]):
            assert nxt.opening_cash == pytest.approx(prev.closing_cash, abs=1e-9)
        # Cash flow carries it: it is cash, so there is no add-back, and CFADS
        # must move by the income between a rate of nil and a live one.
        none = run_lbo(_hoarder(rich_deal, rate=0.0))
        assert r.years[0].cash_available_for_debt_service > (
            none.years[0].cash_available_for_debt_service)

    def test_it_raises_the_return(self, rich_deal):
        assert sponsor_irr(run_lbo(_hoarder(rich_deal))) > sponsor_irr(
            run_lbo(_hoarder(rich_deal, rate=0.0)))


class TestWhatTaxDoesWithIt:
    def test_it_is_taxable_when_the_cap_is_not_binding(self, rich_deal):
        d = _hoarder(rich_deal)
        d.interest_limitation = InterestLimitation(enabled=False)
        idle = d.model_copy(deep=True)
        idle.cash_deposit_rate = 0.0

        earning, idle = run_lbo(d).years[0], run_lbo(idle).years[0]
        assert earning.ebt > idle.ebt
        assert earning.taxes > idle.taxes

    def test_a_capped_borrower_pays_no_tax_on_it(self, rich_deal):
        """Not a bug — the arithmetic of §163(j). A dollar of interest income
        raises taxable income by a dollar AND the deductible capacity by a
        dollar, so a borrower already at the cap keeps the whole of it. The
        exemption disappears the moment the cap stops binding, which is the
        version tested above."""
        earning = run_lbo(_hoarder(rich_deal)).years[0]
        idle = run_lbo(_hoarder(rich_deal, rate=0.0)).years[0]

        assert earning.interest_cf_closing > 0, "the cap must still be binding"
        assert earning.ebt > idle.ebt
        assert earning.taxes == pytest.approx(idle.taxes, abs=1e-9)

    def test_it_adds_to_the_163j_capacity_rather_than_netting_off_ati(self, rich_deal):
        """Business interest INCOME is added to the cap dollar for dollar. It is
        not deducted from the expense and not netted into ATI — which is why a
        cash-rich borrower is less often limited."""
        d = _hoarder(rich_deal)
        assert d.interest_limitation.enabled
        for y in run_lbo(d).years:
            ati = y.ebit - y.revolver_undrawn_fee
            assert y.interest_capacity == pytest.approx(
                y.interest_income + 0.30 * max(ati, 0.0), abs=1e-6
            )

    def test_ati_itself_is_struck_before_the_income(self, rich_deal):
        """ATI is computed without regard to business interest income. Netting
        it in would give the borrower 30 cents of extra capacity per dollar
        earned instead of a full dollar."""
        earning = run_lbo(_hoarder(rich_deal)).years[0]
        idle = run_lbo(_hoarder(rich_deal, rate=0.0)).years[0]
        # EBIT is identical between the two — the income sits below it.
        assert earning.ebit == pytest.approx(idle.ebit, abs=1e-9)
        assert earning.interest_capacity - idle.interest_capacity == pytest.approx(
            earning.interest_income, abs=1e-6
        )

    def test_the_capacity_gain_is_real_when_the_cap_binds(self, rich_deal):
        d = _hoarder(rich_deal)
        assert run_lbo(d).years[0].interest_cf_closing < run_lbo(
            _hoarder(rich_deal, rate=0.0)).years[0].interest_cf_closing

    def test_nothing_changes_when_the_cap_is_off(self, rich_deal):
        d = _hoarder(rich_deal)
        d.interest_limitation = InterestLimitation(enabled=False)
        for y in run_lbo(d).years:
            assert y.interest_deducted == pytest.approx(y.business_interest, abs=1e-9)

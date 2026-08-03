"""§163(j): the cap on deductible business interest.

The provision that binds hardest on a modern US LBO. These tests pin the four
things a practitioner would check before believing the output: what the cap
reaches, what it excludes, what happens to the interest it denies, and which
way each switch moves the answer.
"""

import pytest

from lbo_engine import Assumptions, InterestLimitation, run_lbo
from lbo_engine.returns import sponsor_irr


def _off(deal: Assumptions) -> Assumptions:
    d = deal.model_copy(deep=True)
    d.interest_limitation = InterestLimitation(enabled=False)
    return d


class TestWhatTheCapReaches:
    def test_business_interest_is_coupon_plus_pik_plus_fee_amortisation(self, rich_deal):
        """Fee amortisation is OID, and OID is interest. Leaving it out would
        overstate the deduction on every deal with an arrangement fee."""
        y = run_lbo(rich_deal).years[0]
        assert y.business_interest == pytest.approx(
            y.cash_interest_total + y.pik_accrual_total + y.fee_amortisation, abs=1e-9
        )

    def test_the_undrawn_commitment_fee_is_outside_the_cap(self, rich_deal):
        """The 2020 final regulations left commitment fees out of the definition
        of interest, so they are deducted in full however tight the cap is."""
        d = rich_deal.model_copy(deep=True)
        d.revolver.commitment = 300.0
        d.revolver.undrawn_fee = 0.02  # large enough that including it would show
        y = run_lbo(d).years[0]

        assert y.revolver_undrawn_fee > 0
        assert y.business_interest == pytest.approx(
            y.cash_interest_total + y.pik_accrual_total + y.fee_amortisation, abs=1e-9
        )
        # ...and it reduces ATI rather than competing for capacity within it.
        assert y.interest_capacity == pytest.approx(
            0.30 * (y.ebit - y.revolver_undrawn_fee), abs=1e-9
        )


class TestTheCapCostsCash:
    def test_a_levered_structure_pays_tax_on_denied_interest(self, rich_deal):
        capped = run_lbo(rich_deal)
        uncapped = run_lbo(_off(rich_deal))

        year = capped.years[0]
        assert year.interest_deducted < year.business_interest, "the cap must bind"
        # Tax is charged on more than book profit — by exactly the denied amount.
        assert year.taxable_income == pytest.approx(
            year.ebt + (year.business_interest - year.interest_deducted), abs=1e-9
        )
        assert year.taxes > uncapped.years[0].taxes

    def test_it_lowers_the_return(self, rich_deal):
        assert sponsor_irr(run_lbo(rich_deal)) < sponsor_irr(run_lbo(_off(rich_deal)))

    def test_a_book_loss_can_still_owe_tax(self, rich_deal):
        """The result that surprises people, and the reason the cap matters:
        interest is still paid, it simply stops sheltering income."""
        d = rich_deal.model_copy(deep=True)
        d.operating.ebitda_margin = [0.192, 0.10, 0.198, 0.200, 0.202]
        d.revolver.commitment = 400.0
        year = run_lbo(d).years[1]

        assert year.ebt < 0
        assert year.taxable_income > 0
        assert year.taxes > 0


class TestTheCarryforward:
    def test_denied_interest_carries_forward_and_never_expires(self, rich_deal):
        r = run_lbo(rich_deal)
        assert r.years[0].interest_cf_closing > 0
        for prev, nxt in zip(r.years, r.years[1:]):
            assert nxt.interest_cf_opening == pytest.approx(prev.interest_cf_closing, abs=1e-9)

    def test_the_carryforward_competes_with_the_current_year(self, rich_deal):
        """It is treated as business interest paid again this year, so it does
        not get its own capacity — it queues for the same capacity."""
        for y in run_lbo(rich_deal).years:
            subject = y.business_interest + y.interest_cf_opening
            assert y.interest_deducted == pytest.approx(
                min(subject, y.interest_capacity), abs=1e-9
            )
            assert y.interest_cf_closing == pytest.approx(
                subject - y.interest_deducted, abs=1e-9
            )

    def test_spare_capacity_releases_it(self, rich_deal):
        """A deleveraging borrower eventually gets the deduction back — late,
        and worth less, but not lost."""
        d = rich_deal.model_copy(deep=True)
        d.hold_years = 5
        r = run_lbo(d)
        released = [
            y for y in r.years if y.interest_cf_closing < y.interest_cf_opening - 1e-9
        ]
        assert released, "amortising debt must eventually free capacity"


class TestTheSwitches:
    def test_a_tighter_percentage_denies_more(self, rich_deal):
        def denied(pct: float) -> float:
            d = rich_deal.model_copy(deep=True)
            d.interest_limitation = InterestLimitation(pct_of_ati=pct)
            return run_lbo(d).years[0].interest_cf_closing

        assert denied(0.10) > denied(0.30) > denied(0.60)

    def test_the_ebitda_basis_is_more_generous_than_ebit(self, rich_deal):
        """The 2022 change from an EBITDA-like ATI to an EBIT-like one, which
        for a capital-intensive borrower cut the cap by a third or more."""
        ebitda_basis = rich_deal.model_copy(deep=True)
        ebitda_basis.interest_limitation = InterestLimitation(ati_basis="ebitda")

        wide = run_lbo(ebitda_basis).years[0]
        narrow = run_lbo(rich_deal).years[0]
        assert wide.interest_capacity > narrow.interest_capacity
        assert wide.interest_capacity - narrow.interest_capacity == pytest.approx(
            0.30 * narrow.da, abs=1e-9
        )
        assert wide.taxes < narrow.taxes

    def test_disabled_deducts_everything(self, rich_deal):
        for y in run_lbo(_off(rich_deal)).years:
            assert y.interest_deducted == pytest.approx(y.business_interest, abs=1e-9)
            assert y.interest_cf_closing == 0.0
            assert y.taxable_income == pytest.approx(y.ebt, abs=1e-9)


class TestItInteractsWithTheRestOfTheModel:
    def test_the_nol_is_computed_after_the_cap_not_before(self, rich_deal):
        """Order matters and is the statute's: §163(j) fixes the tax base, then
        §172(a) shelters a share of it. Reversing them would shelter income the
        company never had."""
        for y in run_lbo(rich_deal).years:
            if y.taxable_income > 0:
                assert y.nol_used == pytest.approx(
                    min(y.nol_opening, rich_deal.nol_limit_pct * y.taxable_income), abs=1e-9
                )

    def test_pik_buys_cash_but_no_tax_relief(self, rich_deal):
        """§163(j) reaches accrued interest, so moving a coupon from cash to PIK
        changes the cash flow and nothing about the deduction. Worth pinning:
        the intuition that PIK is 'non-cash, so it does not cost anything' is
        wrong in exactly this place."""
        cash_pay = rich_deal.model_copy(deep=True)
        cash_pay.tranches[-1].cash_rate = 0.11
        cash_pay.tranches[-1].pik_rate = 0.0
        # Interest struck on opening balances, so the two structures enter year
        # one identically levered and the ONLY difference left is the tax
        # treatment. On average balances the comparison is confounded: cash
        # interest spent is cash not swept, so the balances themselves diverge.
        cash_pay.interest_on_average_balance = False

        accruing = cash_pay.model_copy(deep=True)
        accruing.tranches[-1].cash_rate = 0.0
        accruing.tranches[-1].pik_rate = 0.11

        a, b = run_lbo(cash_pay).years[0], run_lbo(accruing).years[0]
        assert b.pik_accrual_total > 0 and a.pik_accrual_total == 0
        assert a.business_interest == pytest.approx(b.business_interest, abs=1e-9)
        assert a.interest_cf_closing == pytest.approx(b.interest_cf_closing, abs=1e-9)
        # The cash flow differs; the deduction does not.
        assert b.cash_available_for_debt_service > a.cash_available_for_debt_service

"""`entry_ebitda` and the operating build must describe the same company.

`entry_ebitda` sets the enterprise value and the size of every tranche.
`entry_revenue × ebitda_margin[0]` is what the projection actually starts from.
Nothing connected them, so a reviewer fed the live API `entry_ebitda=0.001` on
an otherwise normal deal and got **200 OK, MOIC 184.34×** — a confident
four-decimal answer to a structurally incoherent deal. The tranches were sized
at nil and the exit was struck on real earnings.

Two responses, and the split matters:

* **Reject** the incoherent end. Nothing describing two different businesses
  should return a number at all.
* **Flag** the legitimate middle. A normalised entry EBITDA is standard — Dollar
  General is priced on the last clean year because the trailing one was
  deliberately depressed — but it silently changes the effective entry multiple,
  so a reader is told rather than left to find it.
"""

import pytest

from api.case_studies import CASES
from api.presets import default_deal
from lbo_engine import Assumptions
from lbo_engine.calibration import check_assumptions


def _with(deal, **changes):
    payload = deal.model_dump()
    payload.update(changes)
    return payload


class TestTheIncoherentEndIsRejected:
    def test_the_exploit_that_returned_184x(self):
        """The exact payload from the review."""
        with pytest.raises(ValueError, match="cannot be reconciled"):
            Assumptions.model_validate(_with(default_deal(), entry_ebitda=0.001))

    def test_absurdly_high_is_rejected_too(self):
        """Symmetric. Pricing on ten times what the business earns is the same
        error running the other way, and would size the debt off a fiction."""
        with pytest.raises(ValueError, match="cannot be reconciled"):
            Assumptions.model_validate(_with(default_deal(), entry_ebitda=10_000.0))

    def test_the_message_names_both_numbers(self):
        """An error that does not say what it compared is a dead end."""
        with pytest.raises(ValueError) as exc:
            Assumptions.model_validate(_with(default_deal(), entry_ebitda=0.001))
        text = str(exc.value)
        assert "implies" in text and "price the deal and run it" in text


class TestTheLegitimateMiddleIsAllowed:
    def test_a_normalised_entry_ebitda_still_runs(self):
        """The band is wide on purpose. Dollar General's real 1.4× gap must not
        be rejected — it is a defensible modelling choice, not an error."""
        deal = Assumptions.model_validate(
            _with(default_deal(), entry_ebitda=default_deal().entry_ebitda * 1.4))
        assert deal.entry_ebitda_gap() == pytest.approx(1.4 * 1.02, rel=0.05)

    def test_but_it_is_flagged(self):
        deal = Assumptions.model_validate(
            _with(default_deal(), entry_ebitda=default_deal().entry_ebitda * 1.4))
        assert "entry_ebitda" in {f.field for f in check_assumptions(deal)}

    def test_a_coherent_deal_is_not_flagged(self):
        assert "entry_ebitda" not in {f.field for f in check_assumptions(default_deal())}

    def test_the_flag_states_the_effective_multiple(self):
        """The number that actually matters: what you paid, on the business the
        model runs. Dollar General's page argues 9.7× versus 16.3× at length and
        never mentions that its own projection implies a third figure."""
        deal = Assumptions.model_validate(
            _with(default_deal(), entry_ebitda=default_deal().entry_ebitda * 1.4))
        message = next(f.message for f in check_assumptions(deal)
                       if f.field == "entry_ebitda")
        effective = deal.entry_multiple * deal.entry_ebitda_gap()
        assert f"{effective:.1f}×" in message
        assert f"{deal.entry_multiple:.1f}×" in message


class TestTheCaseStudies:
    @pytest.mark.parametrize("case", [pytest.param(c, id=c.slug) for c in CASES])
    def test_every_case_is_coherent_enough_to_run(self, case):
        for column in ("underwriting", "realised"):
            deal = getattr(case, column)
            if deal is not None:
                assert 0.25 < deal.entry_ebitda_gap() < 4.0, f"{case.slug}/{column}"

    def test_dollar_general_surfaces_its_normalisation(self):
        """The case that prompted this. It is priced on fiscal 2005 and projects
        from fiscal 2006 — a real, defensible, and previously invisible gap."""
        dg = next(c for c in CASES if c.slug.startswith("dollar"))
        assert dg.underwriting.entry_ebitda_gap() > 1.15
        assert "entry_ebitda" in {f.field for f in check_assumptions(dg.underwriting)}

    def test_a_deal_priced_on_what_it_earns_stays_quiet(self):
        """Most cases should NOT flag, or the flag is noise."""
        quiet = [c for c in CASES
                 if "entry_ebitda" not in {f.field for f in check_assumptions(c.underwriting)}]
        assert len(quiet) >= 3, [c.slug for c in quiet]

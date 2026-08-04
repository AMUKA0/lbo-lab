"""The case studies, exported as live Excel models.

"Here is Hilton 2007 as an auditable spreadsheet" is a better thing to hand
someone than a web page, and it is only worth handing over if the file cannot
drift from the page. So these tests assert two things:

1. **Every column exports**, including the three that break — as a schedule up
   to the break, which is what the web page already shows.
2. **The workbook agrees with the case's own published figures**, so the site
   and the file cannot say different things about the same deal.

The second is the one that earns its keep. Numbers on a case page come from the
engine; numbers in the workbook come from Excel formulas. They are two
implementations, and without a test tying them together they diverge quietly.
"""

import io

import pytest

from api.case_studies import CASES
from lbo_engine import run_lbo
from lbo_engine.partial import survivable_years, truncate
from lbo_engine.workbook import build_partial_workbook, workbook_bytes

openpyxl = pytest.importorskip("openpyxl")


def _columns():
    for case in CASES:
        for name in ("underwriting", "realised"):
            deal = getattr(case, name)
            if deal is not None:
                yield pytest.param(case, name, deal, id=f"{case.slug}-{name}")


COLUMNS = list(_columns())


def _survives(deal) -> bool:
    try:
        run_lbo(deal)
        return True
    except ValueError:
        return False


@pytest.mark.parametrize("case,name,deal", COLUMNS)
def test_every_column_exports(case, name, deal):
    """Including the ones that break. A case library where a third of the
    columns cannot be downloaded is a library with a hole in it, and the hole
    is exactly where the interesting deals are."""
    payload = workbook_bytes(deal, allow_partial=True)
    assert payload[:2] == b"PK"
    assert len(payload) > 8_000


@pytest.mark.parametrize("case,name,deal", COLUMNS)
def test_a_broken_column_says_so_on_every_sheet_that_matters(case, name, deal):
    """A partial model that does not announce itself is the most dangerous file
    in this project: every number on it is arithmetically right, and the
    conclusion someone would draw from it is wrong."""
    if _survives(deal):
        pytest.skip("this column survives its hold")

    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes(deal, allow_partial=True)))

    banner = " ".join(
        str(wb["Inputs"].cell(row=r, column=1).value or "") for r in range(1, 10)
    )
    assert "PARTIAL MODEL" in banner
    assert f"{deal.hold_years}-year hold" in banner

    returns = " ".join(
        str(wb["Returns"].cell(row=r, column=1).value or "") for r in range(1, 12)
    )
    assert "No exit, and therefore no return" in returns
    # And nothing that could be mistaken for one.
    for row in wb["Returns"].iter_rows(min_col=2, max_col=4):
        for cell in row:
            assert cell.value is None, f"{case.slug}/{name}: a number survived on Returns"


@pytest.mark.parametrize("case,name,deal", COLUMNS)
def test_a_partial_export_stops_exactly_at_the_break(case, name, deal):
    if _survives(deal):
        pytest.skip("this column survives its hold")

    survived = survivable_years(deal)
    assert survived > 0
    run_lbo(truncate(deal, survived))  # the truncated deal must itself be sound
    with pytest.raises(ValueError):
        run_lbo(truncate(deal, survived + 1))


class TestTheFileAgreesWithThePage:
    """The load-bearing pair. Both read the same engine, but through different
    paths — the page through `run_lbo`, the file through Excel formulas
    recalculated independently — so agreement is evidence, not tautology."""

    def _recalculate(self, deal, tmp_path, name: str):
        formulas = pytest.importorskip("formulas")

        # The recalculation runs on the opening-balance convention, which is
        # acyclic; the average-balance variant is genuinely circular and
        # `formulas` reports #CIRC! rather than iterating the way Excel does.
        acyclic = deal.model_copy(deep=True)
        acyclic.interest_on_average_balance = False

        path = str(tmp_path / f"{name}.xlsx")
        try:
            wb = build_partial_workbook(acyclic) if not _survives(acyclic) else None
        except ValueError:
            pytest.skip("cannot service even one year")
        if wb is None:
            from lbo_engine.workbook import build_workbook

            wb = build_workbook(acyclic)
        wb.save(path)

        solution = formulas.ExcelModel().loads(path).finish().calculate()
        book = openpyxl.load_workbook(path)
        base = f"{name}.xlsx"

        def value(sheet: str, cell: str) -> float:
            v = solution[f"'[{base}]{sheet.upper()}'!{cell}"]
            try:
                return float(v.value[0, 0])
            except Exception:
                return float(v)

        def row(sheet: str, label: str) -> int:
            hits = [r[0].row for r in book[sheet].iter_rows(min_col=1, max_col=1)
                    if r[0].value == label]
            assert hits, f"no row labelled {label!r} on {sheet}"
            return hits[-1]

        modelled = acyclic if _survives(acyclic) else truncate(
            acyclic, survivable_years(acyclic))
        return value, row, run_lbo(modelled)

    @pytest.mark.parametrize("case,name,deal", COLUMNS)
    def test_the_schedule_recalculates_to_the_engine(self, case, name, deal, tmp_path):
        value, row, result = self._recalculate(deal, tmp_path, f"{case.slug}-{name}")

        for i, year in enumerate(result.years):
            c = chr(ord("B") + i)
            for label, expected in (
                ("EBITDA", year.ebitda),
                ("Taxable income", year.taxable_income),
                ("Closing cash", year.closing_cash),
                ("Net debt", year.total_debt_closing - year.closing_cash),
            ):
                assert value("Model", f"{c}{row('Model', label)}") == pytest.approx(
                    expected, abs=1e-3), f"{case.slug}/{name} year {year.year} {label}"

    @pytest.mark.parametrize("case,name,deal", COLUMNS)
    def test_the_entry_equity_matches_the_published_cheque(self, case, name, deal, tmp_path):
        """The one figure a reader will check against the case page first, and
        the one that would embarrass the project most if the file disagreed."""
        value, row, result = self._recalculate(deal, tmp_path, f"{case.slug}-{name}")
        assert value("S&U", f"B{row('S&U', 'Sponsor equity (the plug)')}") == (
            pytest.approx(result.entry_equity, abs=1e-3)
        )

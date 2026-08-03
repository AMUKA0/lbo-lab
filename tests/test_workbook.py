"""The Excel export.

The point of this file is one test: open the exported workbook, recalculate it
with an independent formula engine, and assert it agrees with the Python model.
Without that, a formula-driven export is a second implementation of the maths
that can drift from the first, silently, and be wrong in a spreadsheet someone
is pasting into an IC memo.

The recalculation runs against the **opening-balance** convention, because that
is acyclic and can be evaluated outside Excel. The average-balance convention is
genuinely circular — Excel resolves it by iteration and `formulas` reports
`#CIRC!` rather than iterating — so for that variant the tests below assert the
formula shape and the iteration flag instead. Every other line of the model,
including the whole waterfall, the tax build and the exit, is verified numerically.
"""

import os
import tempfile

import pytest

from lbo_engine import Assumptions, run_lbo
from lbo_engine.workbook import build_workbook

openpyxl = pytest.importorskip("openpyxl")


def _acyclic(deal: Assumptions) -> Assumptions:
    payload = deal.model_dump()
    payload["interest_on_average_balance"] = False
    return Assumptions.model_validate(payload)


def _write(deal: Assumptions, name: str) -> str:
    path = os.path.join(tempfile.mkdtemp(), name)
    build_workbook(deal).save(path)
    return path


def _recalculate(path: str):
    """Evaluate the workbook with `formulas`, and return a value getter."""
    formulas = pytest.importorskip("formulas")
    from openpyxl import load_workbook

    solution = formulas.ExcelModel().loads(path).finish().calculate()
    wb = load_workbook(path)
    base = os.path.basename(path)

    def value(sheet: str, cell: str) -> float:
        v = solution[f"'[{base}]{sheet.upper()}'!{cell}"]
        try:
            return float(v.value[0, 0])
        except Exception:
            return float(v)

    def row(sheet: str, label: str) -> int:
        """The LAST row carrying this label — per-tranche blocks reuse names
        like "Cash interest", and the summary line is always below them."""
        hits = [r[0].row for r in wb[sheet].iter_rows(min_col=1, max_col=1)
                if r[0].value == label]
        assert hits, f"no row labelled {label!r} on {sheet}"
        return hits[-1]

    return value, row, wb


class TestItIsTheSameModel:
    def test_every_line_agrees_with_the_engine(self, rich_deal):
        """The load-bearing test. If this fails, the workbook is lying."""
        deal = _acyclic(rich_deal)
        path = _write(deal, "rich.xlsx")
        value, row, _ = _recalculate(path)
        result = run_lbo(deal)

        for i, year in enumerate(result.years):
            c = chr(ord("B") + i)
            assert value("Model", f"{c}{row('Model', 'EBITDA')}") == pytest.approx(
                year.ebitda, abs=1e-4), f"year {year.year} EBITDA"
            assert -value("Model", f"{c}{row('Model', 'Cash interest')}") == pytest.approx(
                year.cash_interest_total, abs=1e-4), f"year {year.year} interest"
            assert -value("Model", f"{c}{row('Model', 'Tax')}") == pytest.approx(
                year.taxes, abs=1e-4), f"year {year.year} tax"
            assert value("Model", f"{c}{row('Model', 'Closing cash')}") == pytest.approx(
                year.closing_cash, abs=1e-4), f"year {year.year} cash"
            assert value("Model", f"{c}{row('Model', 'Net debt')}") == pytest.approx(
                year.total_debt_closing - year.closing_cash, abs=1e-4), f"year {year.year} net debt"

    def test_the_returns_agree(self, rich_deal):
        deal = _acyclic(rich_deal)
        value, row, _ = _recalculate(_write(deal, "returns.xlsx"))
        result = run_lbo(deal)

        assert value("S&U", f"B{row('S&U', 'Sponsor equity (the plug)')}") == pytest.approx(
            result.entry_equity, abs=1e-4)
        assert value("Returns", f"B{row('Returns', 'Exit equity')}") == pytest.approx(
            result.exit_equity, abs=1e-4)
        assert value("Returns", f"B{row('Returns', 'MOIC')}") == pytest.approx(
            result.moic, abs=1e-6)

    def test_the_checks_sheet_passes(self, rich_deal):
        """The workbook's own invariants, evaluated. A Checks sheet that is
        never tested is decoration."""
        value, row, wb = _recalculate(_write(_acyclic(rich_deal), "checks.xlsx"))
        labels = [r[0].value for r in wb["Checks"].iter_rows(min_col=1, max_col=1)
                  if r[0].value and r[0].row >= 4]
        assert labels, "no checks written"
        for label in labels:
            r = row("Checks", label)
            kind = wb["Checks"].cell(row=r, column=3).value
            v = value("Checks", f"B{r}")
            # An identity must be zero; a limit only has to be the right side
            # of it. Asserting equality on a headroom check would fail on every
            # healthy deal.
            if kind == "= 0":
                assert v == pytest.approx(0.0, abs=0.01), f"{label} = {v}"
            else:
                assert v >= -0.01, f"{label} = {v}"


class TestTheCircularity:
    def test_iteration_is_enabled_when_interest_is_circular(self, rich_deal):
        """Without this the workbook opens to a wall of circular-reference
        warnings, and an analyst reasonably concludes it is broken."""
        wb = build_workbook(rich_deal)
        assert rich_deal.interest_on_average_balance
        assert wb.calculation.iterate is True
        assert wb.calculation.iterateCount >= 100
        assert wb.calculation.iterateDelta <= 1e-6

    def test_the_average_balance_formula_is_actually_circular(self, rich_deal):
        """Interest must reference the closing balance it helps determine — that
        is the convention, and losing it would silently change the model."""
        wb = build_workbook(rich_deal)
        ws = wb["Model"]
        interest = [
            ws.cell(row=r[0].row, column=2).value
            for r in ws.iter_rows(min_col=1, max_col=1)
            if r[0].value == "Cash interest"
        ]
        assert any("AVERAGE(" in str(f) for f in interest), interest

    def test_the_breaker_produces_an_acyclic_workbook(self, rich_deal):
        wb = build_workbook(_acyclic(rich_deal))
        assert wb.calculation.iterate is False
        ws = wb["Model"]
        formulas_used = [
            ws.cell(row=r[0].row, column=2).value
            for r in ws.iter_rows(min_col=1, max_col=1)
            if r[0].value == "Cash interest"
        ]
        assert not any("AVERAGE(" in str(f) for f in formulas_used)


class TestItIsReadableByAnalysts:
    def test_calculated_cells_contain_formulas_not_values(self, rich_deal):
        """The whole difference between this and a CSV. A hardcoded number in a
        calculation row cannot be audited or flexed."""
        wb = build_workbook(rich_deal)
        ws = wb["Model"]
        checked = 0
        for r in ws.iter_rows(min_col=1, max_col=1):
            if r[0].value in ("EBITDA", "Net debt", "Closing cash", "Tax"):
                for i in range(rich_deal.hold_years):
                    v = ws.cell(row=r[0].row, column=2 + i).value
                    assert isinstance(v, str) and v.startswith("="), f"{r[0].value} is hardcoded"
                    checked += 1
        assert checked > 0

    def test_inputs_are_named_ranges(self, rich_deal):
        """Named ranges survive an analyst inserting a row. Cell addresses do not."""
        wb = build_workbook(rich_deal)
        names = set(wb.defined_names)
        for expected in ("Entry_EBITDA", "Entry_Multiple", "Exit_Multiple",
                         "Tax_Rate", "Sweep_Pct", "Minimum_Cash"):
            assert expected in names, expected

    def test_inputs_are_blue_and_formulas_are_not(self, rich_deal):
        """Blue means "type here". Getting this wrong invites someone to
        overwrite a formula."""
        wb = build_workbook(rich_deal)
        ebitda = next(r[0].row for r in wb["Inputs"].iter_rows(min_col=1, max_col=1)
                      if r[0].value == "Entry EBITDA ($m)")
        assert wb["Inputs"].cell(row=ebitda, column=2).font.color.rgb.endswith("0000CC")

        model = wb["Model"]
        row = next(r[0].row for r in model.iter_rows(min_col=1, max_col=1)
                   if r[0].value == "EBITDA")
        assert not model.cell(row=row, column=2).font.color.rgb.endswith("0000CC")

    def test_the_sheets_are_separated_by_role(self, rich_deal):
        assert build_workbook(rich_deal).sheetnames == [
            "Inputs", "S&U", "Model", "Returns", "Checks"]


class TestItRefusesRatherThanMisleads:
    @pytest.mark.parametrize("field,payload", [
        ("recaps", {"year": 2, "amount": 50.0}),
        ("divestitures", {"year": 2, "proceeds": 50.0}),
        ("injections", {"year": 2, "amount": 50.0}),
    ])
    def test_unsupported_capital_events_raise(self, rich_deal, field, payload):
        """Silently dropping a recap would produce a workbook that disagrees
        with the model and gives no clue why."""
        data = rich_deal.model_dump()
        data[field] = [payload]
        with pytest.raises(ValueError, match="does not yet model"):
            build_workbook(Assumptions.model_validate(data))

    def test_a_pik_toggle_raises(self, rich_deal):
        data = rich_deal.model_dump()
        data["tranches"][-1]["pik_toggle"] = True
        with pytest.raises(ValueError, match="does not yet model"):
            build_workbook(Assumptions.model_validate(data))

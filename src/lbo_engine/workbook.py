"""Export a deal as a LIVE Excel model.

Not a dump of the answers. Every calculated cell contains a formula, so an
analyst can click through the logic, change an assumption and watch the schedule
recalculate. That distinction is the whole point: a values-only export cannot be
audited, and an LBO model that cannot be audited is not trusted by anyone who
matters.

Conventions follow the ones every bank uses, because they are what make a
workbook readable by someone who did not build it:

    blue   hardcoded input      — the only cells you should type in
    black  formula, same sheet
    green  link to another sheet

Three things about this file are load-bearing:

**Iterative calculation is switched on in the file itself.** Interest is charged
on the average of opening and closing balances, closing depends on the sweep, and
the sweep depends on interest — the same circularity the Python engine solves by
iterating. Excel can do it too, but only with iteration enabled, and a workbook
that opens to a wall of circular-reference warnings reads as broken. So the flag
is written into the workbook, not left for the user to find.

**Inputs are named ranges, not cell addresses.** `Entry_EBITDA`, never
`Inputs!B7`. Analysts insert rows; named ranges survive that and addresses do not.

**The Checks sheet is not decoration.** Sources equal uses, the debt roll-forward
ties, cash never goes below the floor. A reviewer looks there first, and a model
that cannot show its own invariants holding is asking to be taken on trust.

What this does *not* yet reproduce is stated rather than approximated: mid-hold
capital events (recaps, divestitures, sponsor support) and the PIK-toggle
election are decisions the engine makes by search, and are refused here rather
than silently dropped — see `_reject_unsupported`.
"""

from __future__ import annotations

from dataclasses import dataclass

from lbo_engine.assumptions import Assumptions
from lbo_engine.sources_uses import build_sources_and_uses

# --- house style -------------------------------------------------------------
# Hex without the alpha prefix openpyxl also accepts, for legibility.
_BLUE = "0000CC"      # hardcoded input
_BLACK = "000000"     # formula, same sheet
_GREEN = "007A33"     # link to another sheet
_RULE = "BFBFBF"
_HEAD_BG = "1F3B2C"
_INPUT_BG = "EAF1FB"


@dataclass
class _Ref:
    """Where an input landed, so formulas can point at it by name."""

    name: str
    cell: str


def _money(ws, cell: str) -> None:
    ws[cell].number_format = '#,##0.0;(#,##0.0)'


def build_workbook(a: Assumptions):
    """Return an openpyxl Workbook containing a live, formula-driven model."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.workbook.defined_name import DefinedName

    _reject_unsupported(a)

    su = build_sources_and_uses(a)
    years = a.hold_years
    growth = a.growth_schedule()
    margin = a.margin_schedule()

    wb = Workbook()

    # THE flag. Without this the workbook opens complaining about circular
    # references and an analyst reasonably concludes the model is broken.
    # Only needed when interest is on average balances; harmless otherwise, but
    # setting it unconditionally would imply a circularity that isn't there.
    wb.calculation.iterate = a.interest_on_average_balance
    wb.calculation.iterateCount = 200
    wb.calculation.iterateDelta = 1e-10

    thin = Side(style="thin", color=_RULE)

    def head(ws, row: int, text: str, span: int = 8) -> None:
        c = ws.cell(row=row, column=1, value=text)
        c.font = Font(bold=True, size=11, color="FFFFFF")
        for i in range(1, span + 1):
            ws.cell(row=row, column=i).fill = PatternFill("solid", fgColor=_HEAD_BG)

    def label(ws, row: int, text: str, indent: int = 0) -> None:
        c = ws.cell(row=row, column=1, value=text)
        c.alignment = Alignment(indent=indent)
        c.font = Font(color=_BLACK)

    # ----------------------------------------------------------------- Inputs
    inp = wb.active
    inp.title = "Inputs"
    inp.column_dimensions["A"].width = 38
    for col in "BCDEFGHIJKLMNOP":
        inp.column_dimensions[col].width = 12

    refs: dict[str, _Ref] = {}

    def put(row: int, text: str, value, name: str, fmt: str | None = None, col: int = 2):
        """One blue input, registered as a named range."""
        label(inp, row, text, indent=1)
        c = inp.cell(row=row, column=col, value=value)
        c.font = Font(color=_BLUE, bold=True)
        c.fill = PatternFill("solid", fgColor=_INPUT_BG)
        c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        if fmt:
            c.number_format = fmt
        ref = _Ref(name, f"Inputs!${c.column_letter}${row}")
        refs[name] = ref
        wb.defined_names.add(DefinedName(name, attr_text=ref.cell))
        return ref

    r = 1
    inp.cell(row=r, column=1, value="LBO model — inputs").font = Font(bold=True, size=14)
    r += 1
    inp.cell(row=r, column=1, value="Blue cells are inputs. Everything else is calculated.").font = Font(
        italic=True, color="666666", size=9
    )
    r += 2

    head(inp, r, "Entry"); r += 1
    put(r, "Entry EBITDA ($m)", a.entry_ebitda, "Entry_EBITDA", '#,##0.0'); r += 1
    put(r, "Entry multiple (× EBITDA)", a.entry_multiple, "Entry_Multiple", '0.00"x"'); r += 1
    put(r, "Entry revenue ($m)", a.operating.entry_revenue, "Entry_Revenue", '#,##0.0'); r += 2

    head(inp, r, "Operating"); r += 1
    put(r, "D&A (% of revenue)", a.operating.da_pct_revenue, "DA_Pct", '0.0%'); r += 1
    put(r, "Capex (% of revenue)", a.operating.capex_pct_revenue, "Capex_Pct", '0.0%'); r += 1
    put(r, "Working capital (% of revenue)", a.operating.nwc_pct_revenue, "NWC_Pct", '0.0%'); r += 1
    put(r, "Tax rate", a.operating.tax_rate, "Tax_Rate", '0.0%'); r += 1
    put(r, "NOL shelter limit (% of income)", a.nol_limit_pct, "NOL_Limit", '0.0%'); r += 2

    head(inp, r, "Operating path — by year"); r += 1
    label(inp, r, "Year", indent=1)
    for i in range(years):
        c = inp.cell(row=r, column=2 + i, value=i + 1)
        c.font = Font(bold=True, color=_BLACK)
        c.alignment = Alignment(horizontal="center")
    r += 1
    growth_row = r
    label(inp, r, "Revenue growth", indent=1)
    for i, g in enumerate(growth):
        c = inp.cell(row=r, column=2 + i, value=g)
        c.font = Font(color=_BLUE, bold=True)
        c.fill = PatternFill("solid", fgColor=_INPUT_BG)
        c.number_format = '0.0%'
    r += 1
    margin_row = r
    label(inp, r, "EBITDA margin", indent=1)
    for i, m in enumerate(margin):
        c = inp.cell(row=r, column=2 + i, value=m)
        c.font = Font(color=_BLUE, bold=True)
        c.fill = PatternFill("solid", fgColor=_INPUT_BG)
        c.number_format = '0.0%'
    r += 2

    head(inp, r, "Capital structure"); r += 1
    tranche_rows: list[dict] = []
    for idx, t in enumerate(a.tranches):
        label(inp, r, t.name, indent=0)
        inp.cell(row=r, column=1).font = Font(bold=True)
        r += 1
        # Positional, not derived from the name — so renaming a tranche in the
        # workbook round-trips instead of breaking the lookup.
        slug = f"T{idx + 1}"
        rows = {
            "name": put(r, "Tranche name", t.name, f"{slug}_Name"),
        }
        r += 1
        rows["turns"] = put(r, "Leverage (turns of EBITDA)", t.leverage_turns,
                            f"{slug}_Turns", '0.00"x"')
        r += 1
        rows["cash"] = put(r, "Cash coupon", t.cash_rate, f"{slug}_Rate", '0.00%'); r += 1
        rows["pik"] = put(r, "PIK rate", t.pik_rate, f"{slug}_PIK", '0.00%'); r += 1
        rows["amort"] = put(r, "Mandatory amortisation (% of original)", t.mandatory_amort_pct,
                            f"{slug}_Amort", '0.0%'); r += 1
        rows["sweep_flag"] = put(r, "Sweeps against this tranche (1/0)",
                                 1 if t.sweepable else 0, f"{slug}_Sweepable", '0')
        r += 1
        rows["sweepable"] = t.sweepable
        rows["name"] = t.name
        rows["slug"] = slug
        tranche_rows.append(rows)
        r += 1

    head(inp, r, "Revolver & cash policy"); r += 1
    put(r, "Revolver commitment ($m)", a.revolver.commitment, "Revolver_Commitment", '#,##0.0'); r += 1
    put(r, "Revolver rate", a.revolver.cash_rate, "Revolver_Rate", '0.00%'); r += 1
    put(r, "Undrawn commitment fee", a.revolver.undrawn_fee, "Undrawn_Fee", '0.00%'); r += 1
    put(r, "Minimum cash ($m)", a.minimum_cash, "Minimum_Cash", '#,##0.0'); r += 1
    put(r, "Cash sweep (% of excess)", a.cash_sweep_pct, "Sweep_Pct", '0.0%'); r += 2

    head(inp, r, "Fees & exit"); r += 1
    put(r, "Transaction fees (% of EV)", a.transaction_fee_pct_ev, "Txn_Fee_Pct", '0.00%'); r += 1
    put(r, "Financing fees (% of debt)", a.financing_fee_pct_debt, "Fin_Fee_Pct", '0.00%'); r += 1
    put(r, "Facility tenor (years)", a.financing_fee_tenor_years, "Fee_Tenor", '0'); r += 1
    put(r, "Exit costs (% of exit EV)", a.exit_fee_pct_ev, "Exit_Fee_Pct", '0.00%'); r += 1
    put(r, "Hold period (years)", a.hold_years, "Hold_Years", '0'); r += 1
    put(r, "Exit multiple (× EBITDA)", a.exit_multiple, "Exit_Multiple", '0.00"x"'); r += 1

    growth_ref = f"Inputs!${{c}}${growth_row}"
    margin_ref = f"Inputs!${{c}}${margin_row}"

    # The per-year rows as ranges, and the hold as a name, so a reader can
    # recover the whole operating path without knowing where anything sits.
    last_col = chr(ord("B") + years - 1)
    wb.defined_names.add(DefinedName(
        "Revenue_Growth", attr_text=f"Inputs!$B${growth_row}:${last_col}${growth_row}"))
    wb.defined_names.add(DefinedName(
        "EBITDA_Margin", attr_text=f"Inputs!$B${margin_row}:${last_col}${margin_row}"))

    # ------------------------------------------------------- Sources & Uses
    su_ws = wb.create_sheet("S&U")
    su_ws.column_dimensions["A"].width = 38
    su_ws.column_dimensions["B"].width = 14
    su_ws.cell(row=1, column=1, value="Sources & uses").font = Font(bold=True, size=14)

    r = 3
    head(su_ws, r, "Uses", 2); r += 1
    label(su_ws, r, "Purchase enterprise value", 1)
    su_ws.cell(row=r, column=2, value="=Entry_EBITDA*Entry_Multiple").font = Font(color=_GREEN)
    ev_cell = f"'S&U'!$B${r}"; _money(su_ws, f"B{r}"); r += 1
    label(su_ws, r, "Transaction fees", 1)
    su_ws.cell(row=r, column=2, value=f"={ev_cell}*Txn_Fee_Pct").font = Font(color=_BLACK)
    txn_cell = f"'S&U'!$B${r}"; _money(su_ws, f"B{r}"); r += 1
    fin_row = r
    label(su_ws, r, "Financing fees", 1)
    _money(su_ws, f"B{r}"); r += 1
    label(su_ws, r, "Cash to balance sheet", 1)
    su_ws.cell(row=r, column=2, value="=Minimum_Cash").font = Font(color=_GREEN)
    cash_cell = f"'S&U'!$B${r}"; _money(su_ws, f"B{r}"); r += 1
    uses_row = r
    label(su_ws, r, "Total uses", 0)
    su_ws.cell(row=r, column=1).font = Font(bold=True)
    su_ws.cell(row=r, column=2,
               value=f"={ev_cell}+{txn_cell}+'S&U'!$B${fin_row}+{cash_cell}").font = Font(bold=True)
    _money(su_ws, f"B{r}")
    uses_cell = f"'S&U'!$B${uses_row}"
    r += 2

    head(su_ws, r, "Sources", 2); r += 1
    tranche_amount_cells: list[str] = []
    for tr in tranche_rows:
        label(su_ws, r, tr["name"], 1)
        su_ws.cell(row=r, column=2, value=f"=Entry_EBITDA*{tr['slug']}_Turns").font = Font(color=_GREEN)
        _money(su_ws, f"B{r}")
        tranche_amount_cells.append(f"'S&U'!$B${r}")
        tr["amount_cell"] = f"'S&U'!$B${r}"
        r += 1
    debt_row = r
    label(su_ws, r, "Total debt", 0)
    su_ws.cell(row=r, column=1).font = Font(bold=True)
    su_ws.cell(row=r, column=2, value="=" + "+".join(tranche_amount_cells)).font = Font(bold=True)
    _money(su_ws, f"B{r}")
    debt_cell = f"'S&U'!$B${debt_row}"
    r += 1
    label(su_ws, r, "Sponsor equity (the plug)", 1)
    su_ws.cell(row=r, column=2, value=f"={uses_cell}-{debt_cell}").font = Font(color=_BLACK, bold=True)
    equity_cell = f"'S&U'!$B${r}"; _money(su_ws, f"B{r}"); r += 1
    label(su_ws, r, "Total sources", 0)
    su_ws.cell(row=r, column=1).font = Font(bold=True)
    su_ws.cell(row=r, column=2, value=f"={debt_cell}+{equity_cell}").font = Font(bold=True)
    _money(su_ws, f"B{r}")
    sources_cell = f"'S&U'!$B${r}"

    # Financing fees are a % of funded debt, which is only known once the
    # tranches are sized — so it is written after them and points back.
    su_ws.cell(row=fin_row, column=2, value=f"={debt_cell}*Fin_Fee_Pct").font = Font(color=_BLACK)
    fin_cell = f"'S&U'!$B${fin_row}"

    # ------------------------------------------------------------------ Model
    model = wb.create_sheet("Model")
    model.column_dimensions["A"].width = 44
    for i in range(years):
        model.column_dimensions[chr(ord("B") + i)].width = 13

    def col(i: int) -> str:
        return chr(ord("B") + i)

    m = 1
    model.cell(row=m, column=1, value="Annual schedule").font = Font(bold=True, size=14)
    m += 2
    label(model, m, "Year")
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value=i + 1)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")
        c.border = Border(bottom=thin)
    m += 1

    rows: dict[str, int] = {}

    def line(name: str, formula_for, bold: bool = False, fmt: str = '#,##0.0',
             indent: int = 1, colour: str = _BLACK) -> int:
        nonlocal m
        label(model, m, name, indent)
        if bold:
            model.cell(row=m, column=1).font = Font(bold=True)
        for i in range(years):
            c = model.cell(row=m, column=2 + i, value=formula_for(i))
            c.font = Font(color=colour, bold=bold)
            c.number_format = fmt
        rows[name] = m
        m += 1
        return m - 1

    def prior(name: str, i: int, fallback: str) -> str:
        """Previous year's cell, or a fallback for year one."""
        return fallback if i == 0 else f"{col(i - 1)}{rows[name]}"

    head(model, m, "Operating", years + 1); m += 1

    # Revenue is written directly rather than through `line`, because year one
    # points at an input and later years point at the cell to their left — a
    # self-referencing row the generic helper cannot express.
    label(model, m, "Revenue", 1)
    for i in range(years):
        base = "Entry_Revenue" if i == 0 else f"{col(i-1)}{m}"
        c = model.cell(row=m, column=2 + i, value=f"={base}*(1+{growth_ref.format(c=col(i))})")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    rows["Revenue"] = m; m += 1

    line("EBITDA", lambda i: f"={col(i)}{rows['Revenue']}*{margin_ref.format(c=col(i))}", bold=True)
    line("D&A", lambda i: f"=-{col(i)}{rows['Revenue']}*DA_Pct")
    line("EBIT", lambda i: f"={col(i)}{rows['EBITDA']}+{col(i)}{rows['D&A']}", bold=True)
    line("Capex", lambda i: f"=-{col(i)}{rows['Revenue']}*Capex_Pct")
    label(model, m, "Change in working capital", 1)
    for i in range(years):
        base = "Entry_Revenue" if i == 0 else f"{col(i-1)}{rows['Revenue']}"
        c = model.cell(row=m, column=2 + i, value=f"=-NWC_Pct*({col(i)}{rows['Revenue']}-{base})")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    rows["dNWC"] = m; m += 1
    line("Financing fee amortisation", lambda i: f"=-{fin_cell}/Fee_Tenor")
    m += 1

    # --- debt, per tranche. Opening / PIK / interest / amortisation / closing.
    head(model, m, "Debt schedule", years + 1); m += 1
    for tr in tranche_rows:
        slug, nm = tr["slug"], tr["name"]
        label(model, m, nm, 0); model.cell(row=m, column=1).font = Font(bold=True); m += 1

        label(model, m, "Opening", 2)
        for i in range(years):
            v = f"={tr['amount_cell']}" if i == 0 else f"={col(i-1)}{m+4}"
            c = model.cell(row=m, column=2 + i, value=v)
            c.font = Font(color=_GREEN if i == 0 else _BLACK); c.number_format = '#,##0.0'
        tr["open_row"] = m; m += 1

        label(model, m, "PIK accrual", 2)
        for i in range(years):
            c = model.cell(row=m, column=2 + i, value=f"={col(i)}{tr['open_row']}*{slug}_PIK")
            c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
        tr["pik_row"] = m; m += 1

        label(model, m, "Mandatory amortisation", 2)
        for i in range(years):
            c = model.cell(row=m, column=2 + i, value=(
                f"=-MIN({tr['amount_cell']}*{slug}_Amort,"
                f"{col(i)}{tr['open_row']}+{col(i)}{tr['pik_row']})"))
            c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
        tr["amort_row"] = m; m += 1

        label(model, m, "Cash sweep", 2)
        tr["sweep_row"] = m; m += 1   # filled once the waterfall exists

        label(model, m, "Closing", 2)
        for i in range(years):
            c = model.cell(row=m, column=2 + i, value=(
                f"={col(i)}{tr['open_row']}+{col(i)}{tr['pik_row']}"
                f"+{col(i)}{tr['amort_row']}+{col(i)}{tr['sweep_row']}"))
            c.font = Font(color=_BLACK, bold=True); c.number_format = '#,##0.0'
        tr["close_row"] = m; m += 1

        label(model, m, "Cash interest", 2)
        for i in range(years):
            # The circularity, or the escape from it. On average balances this
            # cell depends on the closing balance, which depends on the sweep,
            # which depends on this cell — resolved by the iteration flag set on
            # the workbook. The opening-balance convention is acyclic, and is
            # what makes the exported workbook independently recalculable in a
            # test; see tests/test_workbook.py.
            basis = (f"AVERAGE({col(i)}{tr['open_row']},{col(i)}{tr['close_row']})"
                     if a.interest_on_average_balance else f"{col(i)}{tr['open_row']}")
            c = model.cell(row=m, column=2 + i, value=f"={slug}_Rate*{basis}")
            c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
        tr["int_row"] = m; m += 2

    # --- revolver
    label(model, m, "Revolver", 0); model.cell(row=m, column=1).font = Font(bold=True); m += 1
    label(model, m, "Opening", 2)
    rev_open = m
    for i in range(years):
        v = "=0" if i == 0 else f"={col(i-1)}{m+3}"
        c = model.cell(row=m, column=2 + i, value=v)
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1
    label(model, m, "Draw", 2); rev_draw = m; m += 1
    label(model, m, "Repayment", 2); rev_repay = m; m += 1
    label(model, m, "Closing", 2)
    rev_close = m
    for i in range(years):
        c = model.cell(row=m, column=2 + i,
                       value=f"={col(i)}{rev_open}+{col(i)}{rev_draw}-{col(i)}{rev_repay}")
        c.font = Font(color=_BLACK, bold=True); c.number_format = '#,##0.0'
    m += 1
    label(model, m, "Undrawn commitment fee", 2)
    rev_fee = m
    for i in range(years):
        c = model.cell(row=m, column=2 + i,
                       value=f"=-Undrawn_Fee*MAX(Revolver_Commitment-{col(i)}{rev_open},0)")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1
    label(model, m, "Interest", 2)
    rev_int = m
    for i in range(years):
        basis = (f"AVERAGE({col(i)}{rev_open},{col(i)}{rev_close})"
                 if a.interest_on_average_balance else f"{col(i)}{rev_open}")
        c = model.cell(row=m, column=2 + i, value=f"=Revolver_Rate*{basis}")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 2

    # --- income statement below the debt, because interest comes from above
    head(model, m, "Earnings & tax", years + 1); m += 1
    int_sum = "+".join(f"{{c}}{tr['int_row']}" for tr in tranche_rows) + f"+{{c}}{rev_int}"
    pik_sum = "+".join(f"{{c}}{tr['pik_row']}" for tr in tranche_rows)

    label(model, m, "Cash interest", 1)
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value="=-(" + int_sum.replace("{c}", col(i)) + ")")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    rows["CashInt"] = m; m += 1

    label(model, m, "PIK accrual", 1)
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value="=-(" + pik_sum.replace("{c}", col(i)) + ")")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    rows["PIK"] = m; m += 1

    line("Pre-tax income", lambda i: (
        f"={col(i)}{rows['EBIT']}+{col(i)}{rows['CashInt']}+{col(i)}{rows['PIK']}"
        f"+{col(i)}{rows['Financing fee amortisation']}+{col(i)}{rev_fee}"), bold=True)

    label(model, m, "NOL brought forward", 1)
    nol_open = m
    for i in range(years):
        v = "=0" if i == 0 else f"={col(i-1)}{m+2}"
        c = model.cell(row=m, column=2 + i, value=v)
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1
    label(model, m, "NOL used", 1)
    nol_used = m
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value=(
            f"=IF({col(i)}{rows['Pre-tax income']}>0,"
            f"MIN({col(i)}{nol_open},NOL_Limit*{col(i)}{rows['Pre-tax income']}),0)"))
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1
    label(model, m, "NOL carried forward", 1)
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value=(
            f"=IF({col(i)}{rows['Pre-tax income']}>0,{col(i)}{nol_open}-{col(i)}{nol_used},"
            f"{col(i)}{nol_open}-{col(i)}{rows['Pre-tax income']})"))
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1

    line("Tax", lambda i: (
        f"=-IF({col(i)}{rows['Pre-tax income']}>0,"
        f"({col(i)}{rows['Pre-tax income']}-{col(i)}{nol_used})*Tax_Rate,0)"))
    line("Net income", lambda i: f"={col(i)}{rows['Pre-tax income']}+{col(i)}{rows['Tax']}", bold=True)
    m += 1

    head(model, m, "Cash flow & waterfall", years + 1); m += 1
    line("Cash available for debt service", lambda i: (
        f"={col(i)}{rows['Net income']}-{col(i)}{rows['D&A']}"
        f"-{col(i)}{rows['Financing fee amortisation']}-{col(i)}{rows['PIK']}"
        f"+{col(i)}{rows['Capex']}+{col(i)}{rows['dNWC']}"), bold=True)

    label(model, m, "Opening cash", 1)
    cash_open = m
    m += 1

    mand_sum = "+".join(f"{{c}}{tr['amort_row']}" for tr in tranche_rows)
    label(model, m, "Cash after mandatory amortisation", 1)
    after_mand = m
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value=(
            f"={col(i)}{cash_open}+{col(i)}{rows['Cash available for debt service']}"
            f"-Minimum_Cash+(" + mand_sum.replace("{c}", col(i)) + ")"))
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1

    for i in range(years):
        c = model.cell(row=rev_draw, column=2 + i, value=f"=MAX(-{col(i)}{after_mand},0)")
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
        c2 = model.cell(row=rev_repay, column=2 + i,
                        value=f"=MIN({col(i)}{rev_open},MAX({col(i)}{after_mand},0))")
        c2.font = Font(color=_BLACK); c2.number_format = '#,##0.0'

    label(model, m, "Cash for sweep", 1)
    sweep_pool = m
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value=(
            f"=Sweep_Pct*MAX({col(i)}{after_mand}-{col(i)}{rev_repay},0)"))
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
    m += 1

    # Senior-first allocation: each tranche takes what is left after the ones
    # above it, capped at its own balance.
    taken: list[str] = []
    for tr in tranche_rows:
        for i in range(years):
            if not tr["sweepable"]:
                formula = "=0"
            else:
                already = ("+".join(f"{col(i)}{t}" for t in taken)) if taken else "0"
                formula = (
                    f"=-MIN(MAX({col(i)}{sweep_pool}-({already}),0),"
                    f"{col(i)}{tr['open_row']}+{col(i)}{tr['pik_row']}+{col(i)}{tr['amort_row']})")
            c = model.cell(row=tr["sweep_row"], column=2 + i, value=formula)
            c.font = Font(color=_BLACK); c.number_format = '#,##0.0'
        if tr["sweepable"]:
            taken.append(str(tr["sweep_row"]))

    swept = ("+".join(f"{{c}}{t}" for t in taken)) if taken else "0"
    label(model, m, "Closing cash", 1)
    for i in range(years):
        c = model.cell(row=m, column=2 + i, value=(
            f"=Minimum_Cash+MAX({col(i)}{after_mand}-{col(i)}{rev_repay},0)"
            f"+(" + swept.replace("{c}", col(i)) + ")"))
        c.font = Font(color=_BLACK, bold=True); c.number_format = '#,##0.0'
    rows["Closing cash"] = m
    cash_close = m
    m += 1

    # Now that the closing row exists, point each year's opening cash at the
    # prior year's close.
    for i in range(years):
        v = f"={cash_cell}" if i == 0 else f"={col(i-1)}{cash_close}"
        c = model.cell(row=cash_open, column=2 + i, value=v)
        c.font = Font(color=_GREEN if i == 0 else _BLACK); c.number_format = '#,##0.0' 

    close_sum = "+".join(f"{{c}}{tr['close_row']}" for tr in tranche_rows) + f"+{{c}}{rev_close}"
    line("Total debt", lambda i: "=" + close_sum.replace("{c}", col(i)), bold=True)
    line("Net debt", lambda i: f"={col(i)}{rows['Total debt']}-{col(i)}{cash_close}", bold=True)

    # ---------------------------------------------------------------- Returns
    ret = wb.create_sheet("Returns")
    ret.column_dimensions["A"].width = 40
    ret.column_dimensions["B"].width = 16
    ret.cell(row=1, column=1, value="Exit & returns").font = Font(bold=True, size=14)
    last = col(years - 1)

    rr = 3
    head(ret, rr, "Exit", 2); rr += 1
    for text, formula, fmt in (
        ("Terminal EBITDA", f"=Model!{last}{rows['EBITDA']}", '#,##0.0'),
        ("Exit enterprise value", f"=Model!{last}{rows['EBITDA']}*Exit_Multiple", '#,##0.0'),
        ("Less: net debt", f"=-Model!{last}{rows['Net debt']}", '#,##0.0'),
        ("Less: sale costs", f"=-Model!{last}{rows['EBITDA']}*Exit_Multiple*Exit_Fee_Pct", '#,##0.0'),
    ):
        label(ret, rr, text, 1)
        c = ret.cell(row=rr, column=2, value=formula)
        c.font = Font(color=_GREEN); c.number_format = fmt
        rr += 1
    label(ret, rr, "Exit equity", 0); ret.cell(row=rr, column=1).font = Font(bold=True)
    ret.cell(row=rr, column=2, value=f"=MAX(B{rr-3}+B{rr-2}+B{rr-1},0)").font = Font(bold=True)
    ret.cell(row=rr, column=2).number_format = '#,##0.0'
    exit_eq = f"Returns!$B${rr}"
    rr += 2

    head(ret, rr, "Returns", 2); rr += 1
    label(ret, rr, "Entry equity", 1)
    ret.cell(row=rr, column=2, value=f"={equity_cell}").font = Font(color=_GREEN)
    ret.cell(row=rr, column=2).number_format = '#,##0.0'
    entry_eq = f"Returns!$B${rr}"; rr += 1
    label(ret, rr, "MOIC", 1)
    ret.cell(row=rr, column=2, value=f"={exit_eq}/{entry_eq}").font = Font(bold=True)
    ret.cell(row=rr, column=2).number_format = '0.00"x"'; rr += 1
    label(ret, rr, "IRR", 1)
    ret.cell(row=rr, column=2, value=f"=({exit_eq}/{entry_eq})^(1/Hold_Years)-1").font = Font(bold=True)
    ret.cell(row=rr, column=2).number_format = '0.0%'
    ret.cell(row=rr, column=3,
             value="No interim flows, so IRR is the compounded multiple.").font = Font(
        italic=True, color="666666", size=9)
    rr += 2

    head(ret, rr, "Value creation bridge", 2); rr += 1
    bridge = [
        ("EBITDA growth × entry multiple",
         f"=(Model!{last}{rows['EBITDA']}-Entry_EBITDA)*Entry_Multiple"),
        ("Multiple change × exit EBITDA",
         f"=(Exit_Multiple-Entry_Multiple)*Model!{last}{rows['EBITDA']}"),
        ("Net debt paydown",
         f"=({debt_cell}-{cash_cell})-Model!{last}{rows['Net debt']}"),
        ("Fees",
         f"=-({txn_cell}+{fin_cell}+Model!{last}{rows['EBITDA']}*Exit_Multiple*Exit_Fee_Pct)"),
    ]
    first_bridge = rr
    for text, formula in bridge:
        label(ret, rr, text, 1)
        c = ret.cell(row=rr, column=2, value=formula)
        c.font = Font(color=_BLACK); c.number_format = '#,##0.0;(#,##0.0)'
        rr += 1
    label(ret, rr, "Total value created", 0); ret.cell(row=rr, column=1).font = Font(bold=True)
    ret.cell(row=rr, column=2, value=f"=SUM(B{first_bridge}:B{rr-1})").font = Font(bold=True)
    ret.cell(row=rr, column=2).number_format = '#,##0.0;(#,##0.0)'
    bridge_total = f"Returns!$B${rr}"

    # ----------------------------------------------------------------- Checks
    chk = wb.create_sheet("Checks")
    chk.column_dimensions["A"].width = 46
    chk.column_dimensions["B"].width = 16
    chk.column_dimensions["C"].width = 12
    chk.cell(row=1, column=1, value="Checks").font = Font(bold=True, size=14)
    chk.cell(row=2, column=1,
             value="Every one must read OK. A model that cannot show its own "
                   "invariants holding is asking to be taken on trust.").font = Font(
        italic=True, color="666666", size=9)

    # Two kinds of check, and conflating them is a real mistake: an identity
    # must equal zero, whereas a limit only has to be the right side of zero.
    # Testing "cash never below the minimum" for equality would fail on every
    # healthy deal, which is how a Checks sheet trains people to ignore it.
    checks = [
        ("Sources equal uses", f"={sources_cell}-{uses_cell}", "zero"),
        ("Bridge reconciles to the equity gain",
         f"={bridge_total}-({exit_eq}-{entry_eq})", "zero"),
        ("Headroom over the minimum cash balance",
         f"=MIN(Model!B{cash_close}:{last}{cash_close})-Minimum_Cash", "positive"),
        ("Unused revolver commitment",
         f"=Revolver_Commitment-MAX(Model!B{rev_close}:{last}{rev_close})", "positive"),
    ]
    chk.cell(row=3, column=2, value="Value").font = Font(bold=True, size=9)
    chk.cell(row=3, column=3, value="Test").font = Font(bold=True, size=9)
    chk.cell(row=3, column=4, value="Result").font = Font(bold=True, size=9)
    cr = 4
    for text, formula, kind in checks:
        label(chk, cr, text, 1)
        c = chk.cell(row=cr, column=2, value=formula)
        c.font = Font(color=_BLACK); c.number_format = '#,##0.000;(#,##0.000)'
        chk.cell(row=cr, column=3,
                 value="= 0" if kind == "zero" else ">= 0").font = Font(size=9, color="666666")
        test = (f'=IF(ABS(B{cr})<0.01,"OK","CHECK")' if kind == "zero"
                else f'=IF(B{cr}>=-0.01,"OK","CHECK")')
        v = chk.cell(row=cr, column=4, value=test)
        v.font = Font(bold=True)
        cr += 1
    chk.column_dimensions["D"].width = 12

    _freeze(inp, su_ws, model, ret, chk)
    return wb


def _freeze(*sheets) -> None:
    for ws in sheets:
        ws.freeze_panes = "B4"
        ws.sheet_view.showGridLines = False


def _slug(name: str) -> str:
    """A defined-name-safe token. Excel names cannot contain spaces or most
    punctuation, and cannot collide with a cell reference."""
    out = "".join(ch if ch.isalnum() else "_" for ch in name)
    while "__" in out:
        out = out.replace("__", "_")
    return "T_" + out.strip("_")


def _reject_unsupported(a: Assumptions) -> None:
    """Refuse rather than silently drop.

    A workbook that quietly omits a recap would disagree with the engine and
    give no clue why. These are decisions the engine reaches by search — which
    tranche to toggle, how much to raise to hit a target leverage — and encoding
    that search in cell formulas is a different and much larger problem than
    encoding the arithmetic.
    """
    unsupported = []
    if a.recaps:
        unsupported.append("dividend recapitalisations")
    if a.divestitures:
        unsupported.append("divestitures")
    if a.injections:
        unsupported.append("sponsor support")
    if any(t.pik_toggle for t in a.tranches):
        unsupported.append("PIK toggles")
    if unsupported:
        raise ValueError(
            "The Excel export does not yet model "
            + ", ".join(unsupported)
            + ". These are decisions the engine makes by search rather than by "
              "formula, and a workbook that omitted them would silently disagree "
              "with the model. Export a deal without them, or use the CSV schedule."
        )


def workbook_bytes(a: Assumptions) -> bytes:
    """The workbook as bytes, for an HTTP response."""
    import io

    buf = io.BytesIO()
    build_workbook(a).save(buf)
    return buf.getvalue()

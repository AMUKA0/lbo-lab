"""Read a deal back out of an exported workbook.

The round trip is the point. An analyst exports a live model, works on it in
Excel where they are fluent, and brings it back — rather than retyping
assumptions into a web form, which nobody does twice.

Everything is located by **named range**, never by cell address. That is not
fastidiousness: analysts insert rows, and a reader keyed to `Inputs!B7` breaks
silently the first time someone adds a line above it, producing a deal that is
subtly wrong rather than obviously broken.

Errors carry the cell. "Invalid input" tells the user nothing when the workbook
has two hundred of them; "Exit_Multiple (Inputs!C31) is 0 — must be greater than
zero" tells them exactly where to click.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lbo_engine.assumptions import (
    Assumptions,
    Covenants,
    DebtTranche,
    Divestiture,
    DividendRecap,
    EquityInjection,
    InterestLimitation,
    OperatingAssumptions,
    RevolverAssumptions,
)


class WorkbookError(ValueError):
    """A workbook that cannot be read, with enough detail to fix it."""

    def __init__(self, problems: list["Problem"]):
        self.problems = problems
        super().__init__("; ".join(p.message for p in problems))


@dataclass(frozen=True)
class Problem:
    name: str
    cell: str | None
    message: str


def read_workbook(source) -> Assumptions:
    """Parse an exported workbook back into `Assumptions`.

    `source` is a path or a file-like object. Raises `WorkbookError` listing
    every problem found, rather than the first — someone fixing a spreadsheet
    wants the whole list, not one round trip per mistake.
    """
    from openpyxl import load_workbook

    wb = load_workbook(source, data_only=False)
    problems: list[Problem] = []

    def location(name: str) -> tuple[str, str] | None:
        """Resolve a defined name to (sheet, cell-or-range)."""
        dn = wb.defined_names.get(name)
        if dn is None:
            for ws in wb.worksheets:
                local = ws.defined_names.get(name) if hasattr(ws, "defined_names") else None
                if local is not None:
                    dn = local
                    break
        if dn is None:
            return None
        try:
            sheet, ref = next(iter(dn.destinations))
        except StopIteration:
            return None
        return sheet, ref

    def number(name: str, *, required: bool = True) -> float | None:
        loc = location(name)
        if loc is None:
            if required:
                problems.append(Problem(name, None, f"{name} is missing from the workbook"))
            return None
        sheet, ref = loc
        cell = wb[sheet][ref.replace("$", "")]
        value = cell.value
        if isinstance(value, str) and value.startswith("="):
            problems.append(Problem(
                name, f"{sheet}!{ref}",
                f"{name} ({sheet}!{ref.replace('$','')}) contains a formula. Inputs must be "
                "typed values — a formula here means the cell was overwritten."))
            return None
        if value is None or not isinstance(value, (int, float)):
            problems.append(Problem(
                name, f"{sheet}!{ref}",
                f"{name} ({sheet}!{ref.replace('$','')}) is {value!r} — expected a number"))
            return None
        return float(value)

    def text(name: str) -> str | None:
        loc = location(name)
        if loc is None:
            return None
        sheet, ref = loc
        value = wb[sheet][ref.replace("$", "")].value
        return str(value) if value is not None else None

    def _scalar_or_path(name: str) -> float | list[float] | None:
        """One value, or a row of them, depending on what the workbook holds."""
        loc = location(name)
        if loc is None:
            problems.append(Problem(name, None, f"{name} is missing from the workbook"))
            return None
        _, ref = loc
        if ":" not in ref:
            return number(name)
        values = series(name)
        if values is None:
            return None
        return values[0] if len(values) == 1 else values

    def series(name: str) -> list[float] | None:
        """A per-year row, read as a range."""
        loc = location(name)
        if loc is None:
            problems.append(Problem(name, None, f"{name} is missing from the workbook"))
            return None
        sheet, ref = loc
        out: list[float] = []
        for row in wb[sheet][ref.replace("$", "")]:
            for cell in row:
                if not isinstance(cell.value, (int, float)):
                    problems.append(Problem(
                        name, f"{sheet}!{cell.coordinate}",
                        f"{name} at {sheet}!{cell.coordinate} is {cell.value!r} — expected a number"))
                    return None
                out.append(float(cell.value))
        # A row of identical values is a flat rate that was expanded on the way
        # out. Collapsing it back keeps the round trip exact and preserves the
        # flat-versus-path distinction the interface offers. The two are
        # arithmetically identical either way.
        if out and all(v == out[0] for v in out):
            return [out[0]]
        return out

    # --- tranches, discovered positionally ---------------------------------
    indices = sorted(
        int(m.group(1))
        for name in wb.defined_names
        if (m := re.fullmatch(r"T(\d+)_Turns", name))
    )
    if not indices:
        problems.append(Problem("tranches", None,
                                "No debt tranches found. This does not look like a workbook "
                                "exported from this model."))

    tranches: list[DebtTranche] = []
    for i in indices:
        name = text(f"T{i}_Name") or f"Tranche {i}"
        turns = number(f"T{i}_Turns")
        # A coupon may be a scalar or a per-year path, and the sheet says which
        # by how many cells the name covers. Reading it as a scalar would take
        # year one and silently discard the rest of the curve.
        rate = _scalar_or_path(f"T{i}_Rate")
        pik = number(f"T{i}_PIK")
        amort = number(f"T{i}_Amort")
        sweepable = number(f"T{i}_Sweepable", required=False)
        if None in (turns, rate, pik, amort):
            continue
        if turns <= 0:
            problems.append(Problem(f"T{i}_Turns", None,
                                    f"{name}: leverage is {turns} — must be greater than zero. "
                                    "Delete the tranche rather than sizing it at nil."))
            continue
        tranches.append(DebtTranche(
            name=name, leverage_turns=turns, cash_rate=rate, pik_rate=pik,
            mandatory_amort_pct=amort, sweepable=bool(sweepable) if sweepable is not None else True,
        ))

    # --- mid-hold capital events -------------------------------------------
    #
    # The exporter writes these as per-year rows and the reader used to ignore
    # them entirely, which made the round trip lossy in the worst possible way:
    # exporting HCA and uploading it back unchanged returned a DIFFERENT deal —
    # the $4.3bn recap silently gone, no warning — and Hilton came back as an
    # unfinanceable structure, because the rescue capital it depends on did not
    # survive the trip. The site rejected its own artefact.
    #
    # Read as amounts rather than as intentions: the sheet holds the quantum the
    # engine resolved, which is what an analyst sees and can override.
    def event_years(name: str) -> list[tuple[int, float]]:
        """Non-zero cells of a per-year event row, as (year, amount)."""
        if location(name) is None:
            return []
        values = series(name)
        if values is None:
            return []
        # `series` collapses an all-identical row to one entry, which for an
        # event row of zeros means "nothing happened".
        if len(values) == 1 and values[0] == 0:
            return []
        return [(i + 1, v) for i, v in enumerate(values) if abs(v) > 1e-9]

    recaps = [
        DividendRecap(year=year, amount=amount)
        for year, amount in event_years("Recap_Raised")
    ]
    injections = [
        EquityInjection(year=year, amount=amount, label="Sponsor support")
        for year, amount in event_years("Injection_Cash")
    ]
    retired = dict(event_years("Injection_Retired"))
    for injection in injections:
        if injection.year in retired:
            injection.debt_retired = retired[injection.year]
    # Debt bought back with no fresh cash is still an injection.
    for year, amount in retired.items():
        if not any(i.year == year for i in injections):
            injections.append(EquityInjection(
                year=year, amount=0.0, debt_retired=amount, label="Sponsor support"))

    divestitures = [
        # The exported row is proceeds NET of costs and tax, so the fee and gain
        # are already inside it. Re-applying them would deduct twice.
        Divestiture(year=year, proceeds=amount, fee_pct=0.0, taxable_gain=0.0,
                    revenue_removed=dict(event_years("Divest_Revenue")).get(year, 0.0))
        for year, amount in event_years("Divest_Net")
    ]

    revolver_rate = _scalar_or_path("Revolver_Rate")
    growth = series("Revenue_Growth")
    margin = series("EBITDA_Margin")
    hold = number("Hold_Years")

    fields = {
        k: number(k) for k in (
            "Entry_EBITDA", "Entry_Multiple", "Entry_Revenue", "DA_Pct", "Capex_Pct",
            "NWC_Pct", "Tax_Rate", "NOL_Limit", "Revolver_Commitment",
            "Undrawn_Fee", "Minimum_Cash", "Deposit_Rate", "Sweep_Pct", "Txn_Fee_Pct", "Fin_Fee_Pct",
            "Fee_Tenor", "Exit_Fee_Pct", "Exit_Multiple",
        )
    }

    # Maintenance covenants. Absent means cov-lite, which is both the model
    # default and what the market actually issued — so a missing block reads as
    # "no maintenance test", not as an error.
    def optional_series(name: str) -> float | list[float] | None:
        if location(name) is None:
            return None
        values = series(name)
        if values is None:
            return None
        return values[0] if len(values) == 1 else values

    covenants = Covenants(
        net_leverage_ceiling=optional_series("Leverage_Covenant"),
        interest_coverage_floor=optional_series("Coverage_Covenant"),
    )

    # §163(j). Optional, so that a workbook exported before the cap existed
    # still reads; absent, the model default applies.
    headroom = number("PIK_Headroom", required=False)

    cap_on = number("Interest_Limit_On", required=False)
    cap_pct = number("Interest_Limit_Pct", required=False)
    cap_da = number("Interest_Limit_DA", required=False)
    limitation = InterestLimitation() if cap_on is None else InterestLimitation(
        enabled=bool(cap_on),
        pct_of_ati=InterestLimitation().pct_of_ati if cap_pct is None else cap_pct,
        ati_basis="ebitda" if cap_da else "ebit",
    )

    if problems:
        raise WorkbookError(problems)

    if hold is not None and growth is not None and len(growth) not in (1, int(hold)):
        raise WorkbookError([Problem(
            "Hold_Years", None,
            f"The hold is {int(hold)} years but the operating path has {len(growth)} "
            "columns. Extend or trim the Revenue growth and EBITDA margin rows to match, "
            "then re-export so the named ranges follow.")])

    try:
        return Assumptions(
            entry_ebitda=fields["Entry_EBITDA"],
            entry_multiple=fields["Entry_Multiple"],
            operating=OperatingAssumptions(
                entry_revenue=fields["Entry_Revenue"],
                revenue_growth=growth[0] if len(growth) == 1 else growth,
                ebitda_margin=margin[0] if len(margin) == 1 else margin,
                da_pct_revenue=fields["DA_Pct"],
                capex_pct_revenue=fields["Capex_Pct"],
                nwc_pct_revenue=fields["NWC_Pct"],
                tax_rate=fields["Tax_Rate"],
            ),
            tranches=tranches,
            revolver=RevolverAssumptions(
                commitment=fields["Revolver_Commitment"],
                cash_rate=revolver_rate,
                undrawn_fee=fields["Undrawn_Fee"],
            ),
            transaction_fee_pct_ev=fields["Txn_Fee_Pct"],
            financing_fee_pct_debt=fields["Fin_Fee_Pct"],
            financing_fee_tenor_years=int(fields["Fee_Tenor"]),
            exit_fee_pct_ev=fields["Exit_Fee_Pct"],
            nol_limit_pct=fields["NOL_Limit"],
            interest_limitation=limitation,
            covenants=covenants,
            recaps=recaps,
            divestitures=divestitures,
            injections=injections,
            minimum_cash=fields["Minimum_Cash"],
            cash_deposit_rate=fields["Deposit_Rate"],
            pik_election_headroom=0.0 if headroom is None else headroom,
            cash_sweep_pct=fields["Sweep_Pct"],
            hold_years=int(hold),
            exit_multiple=fields["Exit_Multiple"],
        )
    except ValueError as exc:
        # Pydantic's own validation, translated back to something a
        # spreadsheet user can act on.
        raise WorkbookError([Problem("validation", None, _humanise(exc))]) from exc


def _humanise(exc: ValueError) -> str:
    """Turn a Pydantic error into one sentence naming the input as the workbook
    labels it, not as the model spells it."""
    labels = {
        "entry_ebitda": "Entry EBITDA", "entry_multiple": "Entry multiple",
        "exit_multiple": "Exit multiple", "hold_years": "Hold period",
        "tax_rate": "Tax rate", "cash_sweep_pct": "Cash sweep",
        "minimum_cash": "Minimum cash", "nol_limit_pct": "NOL shelter limit",
        "entry_revenue": "Entry revenue", "capex_pct_revenue": "Capex",
        "da_pct_revenue": "D&A", "nwc_pct_revenue": "Working capital",
    }
    text = str(exc)
    for field, label in labels.items():
        if field in text:
            reason = "must be greater than zero"
            if "less than 1" in text:
                reason = "must be below 100% — enter 5% rather than 5"
            elif "less than or equal" in text:
                reason = "is outside the permitted range"
            return f"{label} {reason}."
    return text.split("\n")[0]

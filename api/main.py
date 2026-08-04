"""LBO Lab HTTP API.

A thin transport layer over `lbo_engine`. Deliberately thin: no financial logic
lives here. Every endpoint validates an `Assumptions` payload (the engine's own
Pydantic contract, so the API schema and the model can never drift apart), calls
the same functions the test suite exercises, and serialises the result.

Endpoints are granular rather than one fat "analyse everything" call, because
the client only pays for the tab it is looking at — the sensitivity grid is ~25
engine runs and there is no reason to compute it while the user reads the debt
schedule.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from lbo_engine import Assumptions, run_lbo
from lbo_engine.analysis import (
    breakeven_exit_multiple,
    credit_stats,
    entry_exit_sensitivity,
    exit_year_profile,
    scenario_set,
    tornado,
)
from lbo_engine.calibration import BENCHMARKS, check_assumptions
from lbo_engine.returns import sponsor_irr

from api.case_studies import BY_SLUG, CASES, SOURCES, CaseStudy
from api.presets import PRESETS, default_deal
from api.serialisation import RunOut, jsonable, run_out

app = FastAPI(
    title="LBO Lab API",
    version="1.0.0",
    # Kept under /api so the SPA catch-all below can own every other path, and
    # so the interactive schema survives being served from the same origin.
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    description=(
        "Deal-level leveraged-buyout modelling. Multi-tranche debt schedule, "
        "cash sweep, the interest circularity solved iteratively, calibration "
        "guardrails, stress testing and attribution."
    ),
)

# The SPA is served from a different origin in development (Vite on :5173).
# In production the static build is served by this same app, so same-origin
# requests never reach this middleware and the list below stays a development
# affordance rather than a permanent hole. If the client is ever hosted
# separately from the API, its origin has to be added here explicitly — the
# list is deliberately not a wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------- request bodies

class SensitivityRequest(BaseModel):
    assumptions: Assumptions
    entry_multiples: list[float] | None = None
    exit_multiples: list[float] | None = None
    steps: int = Field(default=5, ge=3, le=11, description="Grid size when multiples are auto-generated")
    span: float = Field(default=2.0, gt=0, le=6, description="Turns either side of the deal's own multiples")


class DealRequest(BaseModel):
    assumptions: Assumptions


class BreakevenRequest(BaseModel):
    assumptions: Assumptions
    target_irr: float = Field(default=0.20, gt=-0.99, lt=5.0)


def _fail(exc: ValueError) -> HTTPException:
    """The engine refuses to print a broken structure. Neither do we — but the
    client needs the reason, not a generic 500, so it can render it as a finding
    rather than a crash."""
    return HTTPException(
        status_code=422,
        detail={"kind": "structure_failure", "message": str(exc)},
    )


def _grid(centre: float, steps: int, span: float) -> list[float]:
    step = (2 * span) / (steps - 1)
    return [round(centre - span + i * step, 4) for i in range(steps)]


# -------------------------------------------------------------------- metadata

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/defaults")
def defaults() -> dict:
    """Everything the client needs to boot: a runnable deal, the preset library,
    and the benchmark bands behind the guardrails (so the UI can show the band
    next to each slider instead of only complaining after the fact)."""
    return {
        "assumptions": default_deal().model_dump(),
        "presets": PRESETS,
        "benchmarks": jsonable(BENCHMARKS),
    }


# ------------------------------------------------------------------- core run

@app.post("/api/run", response_model=RunOut)
def run(req: DealRequest) -> RunOut:
    """One deal, fully modelled: sources & uses, the complete annual schedule
    with per-tranche detail, exit, returns, the value bridge and credit stats."""
    a = req.assumptions
    try:
        result = run_lbo(a)
    except ValueError as exc:
        raise _fail(exc) from exc

    credit = credit_stats(a).reset_index().to_dict(orient="records")
    return run_out(result, check_assumptions(a), jsonable(credit))


@app.post("/api/sensitivity")
def sensitivity(req: SensitivityRequest) -> dict:
    """IRR across entry multiple (rows) × exit multiple (columns).

    Changing the entry multiple re-levers the deal — debt is sized in turns of
    EBITDA, so a richer price means a bigger cheque, not more debt.
    """
    a = req.assumptions
    entries = req.entry_multiples or _grid(a.entry_multiple, req.steps, req.span)
    exits = req.exit_multiples or _grid(a.exit_multiple, req.steps, req.span)
    entries = [m for m in entries if m > 0]
    exits = [m for m in exits if m > 0]

    df = entry_exit_sensitivity(a, entries, exits)
    return {
        "entry_multiples": entries,
        "exit_multiples": exits,
        # Row-major: values[i][j] is entry_multiples[i] × exit_multiples[j].
        # null where the structure fails or the sponsor is wiped out.
        "values": jsonable(df.values.tolist()),
    }


@app.post("/api/tornado")
def tornado_endpoint(req: DealRequest) -> dict:
    """One-at-a-time driver swings, ranked by the width of the IRR span."""
    df = tornado(req.assumptions).reset_index()
    return {"drivers": jsonable(df.to_dict(orient="records"))}


@app.post("/api/scenarios")
def scenarios(req: DealRequest) -> dict:
    """Base / upside / downside / recession, run side by side.

    Each case reports whether the structure survived, not just its IRR — a case
    that breaks the capital structure is the finding, and reporting only the
    cases that happened to compute would hide exactly the ones that matter.
    """
    out = []
    for name, variant in scenario_set(req.assumptions).items():
        record: dict = {"name": name, "failed": False, "message": None}
        try:
            result = run_lbo(variant)
            wiped = result.exit_equity <= 0
            last = result.years[-1]
            coverage = [
                y.ebitda / y.cash_interest_total
                for y in result.years
                if y.cash_interest_total > 0
            ]
            record.update(
                {
                    "irr": None if wiped else sponsor_irr(result),
                    "moic": None if wiped else result.moic,
                    "entry_equity": result.entry_equity,
                    "exit_equity": result.exit_equity,
                    "exit_ebitda": result.exit_ebitda,
                    "exit_multiple": variant.exit_multiple,
                    "exit_net_leverage": (
                        result.exit_net_debt / last.ebitda if last.ebitda else None
                    ),
                    "min_interest_coverage": min(coverage) if coverage else None,
                    "wiped_out": wiped,
                }
            )
        except ValueError as exc:
            record.update(
                {
                    "failed": True,
                    "message": str(exc),
                    "irr": None,
                    "moic": None,
                    "entry_equity": None,
                    "exit_equity": None,
                    "exit_ebitda": None,
                    "exit_multiple": variant.exit_multiple,
                    "exit_net_leverage": None,
                    "min_interest_coverage": None,
                    "wiped_out": True,
                }
            )
        out.append(jsonable(record))
    return {"scenarios": out}


@app.post("/api/exit-profile")
def exit_profile(req: DealRequest) -> dict:
    """IRR and MOIC by exit year: deleveraging compounds MOIC while
    annualisation drags IRR — the hold-longer-versus-flip tension, shown."""
    df = exit_year_profile(req.assumptions).reset_index()
    return {"years": jsonable(df.to_dict(orient="records"))}


@app.post("/api/breakeven")
def breakeven(req: BreakevenRequest) -> dict:
    """The model in reverse: the exit multiple that clears a target IRR.

    The gap between that and the entry multiple is the honest question — how
    much of the return are you asking the market to hand you?
    """
    a = req.assumptions
    value = breakeven_exit_multiple(a, req.target_irr)
    reachable = not math.isnan(value)
    return {
        "target_irr": req.target_irr,
        "breakeven_exit_multiple": value if reachable else None,
        "entry_multiple": a.entry_multiple,
        "assumed_exit_multiple": a.exit_multiple,
        "expansion_required": (value - a.entry_multiple) if reachable else None,
        "reachable": reachable,
    }


@app.post("/api/model.xlsx")
def model_xlsx(req: DealRequest) -> StreamingResponse:
    """The deal as a LIVE Excel model — formulas, not values.

    The distinction is the point. A values export cannot be audited or flexed,
    and in this industry a model you cannot click through is not trusted. Here
    every calculated cell carries a formula, inputs are blue named ranges, and
    iterative calculation is switched on in the file because interest on average
    balances is circular in Excel exactly as it is here.
    """
    from lbo_engine.workbook import workbook_bytes

    try:
        payload = workbook_bytes(req.assumptions)
    except ValueError as exc:
        # Unsupported capital events are refused rather than silently dropped,
        # so this is a describable finding, not a crash.
        raise HTTPException(
            status_code=422,
            detail={"kind": "export_unsupported", "message": str(exc)},
        ) from exc

    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="lbo-model.xlsx"'},
    )


@app.post("/api/import.xlsx")
async def import_xlsx(file: UploadFile = File(...)) -> dict:
    """Read a deal back out of an exported workbook.

    The round trip is the point: an analyst works in Excel, where they are
    fluent, and brings the result back rather than retyping assumptions into a
    form. Problems come back as a list with cell references, because someone
    fixing a spreadsheet wants every mistake at once, not one round trip each.
    """
    import io as _io

    from lbo_engine.workbook_read import WorkbookError, read_workbook

    payload = await file.read()
    if len(payload) > 5_000_000:
        raise HTTPException(
            status_code=413,
            detail={"kind": "too_large", "message": "Workbooks are capped at 5MB."},
        )
    try:
        deal = read_workbook(_io.BytesIO(payload))
    except WorkbookError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "kind": "workbook_invalid",
                "message": "This workbook could not be read.",
                "problems": [
                    {"field": p.name, "cell": p.cell, "message": p.message}
                    for p in exc.problems
                ],
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "kind": "workbook_invalid",
                "message": "That file could not be opened as an Excel workbook.",
                "problems": [],
            },
        ) from exc

    return {"assumptions": deal.model_dump()}


@app.post("/api/schedule.csv")
def schedule_csv(req: DealRequest) -> StreamingResponse:
    """The annual schedule as CSV — the format anyone reviewing this will
    immediately paste into Excel to check the maths."""
    try:
        result = run_lbo(req.assumptions)
    except ValueError as exc:
        raise _fail(exc) from exc

    buffer = io.StringIO()
    result.to_dataframe().to_csv(buffer)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="lbo-schedule.csv"'},
    )


# ------------------------------------------------------------- case studies
#
# Four real buyouts replayed through the same engine. Each case is modelled
# twice — once on assumptions reconstructed from pre-close information only, and
# once on the operating path that actually occurred — so the client can show the
# no-hindsight verdict and the model's own accuracy as two separate questions.
#
# The cases are static, so the replays are cached: the library is eight engine
# runs in total and there is no reason to repeat them per request.


def _truncate(a: Assumptions, years: int) -> Assumptions:
    """The same deal over a shorter hold.

    EVERY per-year schedule has to come with it, not just the operating ones.
    A covenant step-down left at full length makes the engine reject the
    shortened deal for the wrong reason — and because the caller is already
    inside an `except ValueError`, that rejection is silently indistinguishable
    from the structure failing in year one. It reported "survived 0 years" on a
    deal that serviced four of them.
    """
    shorter = a.model_copy(deep=True)
    shorter.hold_years = years
    shorter.operating.revenue_growth = a.growth_schedule()[:years]
    shorter.operating.ebitda_margin = a.margin_schedule()[:years]
    for name in ("net_leverage_ceiling", "interest_coverage_floor"):
        schedule = a.covenant_schedule(name)
        if schedule is not None:
            setattr(shorter.covenants, name, schedule[:years])
    return shorter


def _survivable_years(a: Assumptions) -> int:
    """The longest hold this structure can actually service.

    A bare "the structure fails" is a dead end that reads like a defect. The
    useful statement is *when* it breaks and how far it got, so the client can
    show the schedule up to that point and the reader can see the liquidity
    draining year by year. Cheap to compute: at most `hold_years` engine runs on
    a deal we already know is small.
    """
    for years in range(a.hold_years - 1, 0, -1):
        try:
            run_lbo(_truncate(a, years))
            return years
        except ValueError:
            continue
    return 0


def _replay(a: Assumptions) -> dict:
    """Run one column.

    A structure the engine refuses to model is a *result* here, not an error.
    Rather than stopping at that, the failure is reported with the year it
    happens, the size of the gap, and a full schedule for the years it did
    survive. That is what a credit committee would actually want — "this breaks
    in year three" is information; "failed" is not.

    `failure_kind` says WHICH wall was hit. A structure that runs out of cash, a
    structure that breaches a leverage covenant while paying every coupon, and a
    structure that cannot refinance a maturity are three different findings with
    three different remedies, and collapsing them loses the interesting part.
    """
    try:
        result = run_lbo(a)
    except ValueError as exc:
        kind = getattr(exc, "kind", "liquidity")
        survived = _survivable_years(a)
        partial = None
        if survived > 0:
            shorter = _truncate(a, survived)
            run = run_lbo(shorter)
            credit = credit_stats(shorter).reset_index().to_dict(orient="records")
            # Deliberately no IRR or MOIC on a partial run: there was no exit in
            # that year, and printing a return for one would be a fabrication.
            partial = run_out(run, check_assumptions(shorter), jsonable(credit))
            # No exit happened, so there is no gain to decompose.
            partial.bridge = None
        return {
            "failed": True,
            "failure_kind": kind,
            "message": str(exc),
            "breaks_in_year": survived + 1,
            "survived_years": survived,
            "irr": None,
            "moic": None,
            "run": None,
            "partial_run": partial,
        }

    wiped = result.exit_equity <= 0
    credit = credit_stats(a).reset_index().to_dict(orient="records")
    return {
        "failed": False,
        "failure_kind": None,
        "message": None,
        "irr": None if wiped else jsonable(sponsor_irr(result)),
        "moic": None if wiped else jsonable(result.moic),
        "wiped_out": wiped,
        "breaks_in_year": None,
        "survived_years": a.hold_years,
        "run": run_out(result, check_assumptions(a), jsonable(credit)),
        "partial_run": None,
    }


def _outcome(case: CaseStudy) -> dict:
    o = case.outcome
    return {
        "exit_route": o.exit_route,
        "exit_year": o.exit_year,
        "holding_years": o.holding_years,
        "realised_moic": o.realised_moic,
        "realised_irr": o.realised_irr,
        "confidence": o.confidence,
        "headline": o.headline,
        "narrative": o.narrative,
    }


# Fields that may legitimately differ between the two columns. Anything outside
# this set differing is drift, not news, and the test suite rejects it.
_MAY_DIFFER = {
    "revenue_growth", "ebitda_margin",   # the news itself
    "hold_years", "exit_multiple",       # when and at what you actually got out
    "recaps", "divestitures", "injections",  # events that happened
}


def _column_deltas(case: CaseStudy) -> list[dict]:
    """Every operating input that differs between the columns, spelled out.

    The claim "same structure, fed the operating path that happened" is only
    worth anything if the reader can see what else moved. Hilton's realised
    column carries 150bp less capex than its underwriting column, and that --
    not the revenue collapse -- is the difference between a deal that runs
    eleven years and one that breaks in year two. It was undisclosed until a
    reviewer found it.
    """
    if case.realised is None:
        return []
    u, r = case.underwriting, case.realised
    out: list[dict] = []

    def add(label, a, b, fmt="{:.1%}"):
        if a != b:
            out.append({"field": label, "underwriting": fmt.format(a), "realised": fmt.format(b)})

    add("Capex (% of revenue)", u.operating.capex_pct_revenue, r.operating.capex_pct_revenue)
    add("D&A (% of revenue)", u.operating.da_pct_revenue, r.operating.da_pct_revenue)
    add("Working capital (% of revenue)", u.operating.nwc_pct_revenue, r.operating.nwc_pct_revenue)
    add("Cash sweep", u.cash_sweep_pct, r.cash_sweep_pct)
    add("Minimum cash", u.minimum_cash, r.minimum_cash, "${:,.0f}m")
    add("Hold", u.hold_years, r.hold_years, "{} years")
    add("Exit multiple", u.exit_multiple, r.exit_multiple, "{:.1f}x")
    return out


def _break_note(case: CaseStudy, column: str) -> dict | None:
    """The account of the year this column breaks, if it breaks."""
    note = next((b for b in case.break_notes if b.column == column), None)
    if note is None:
        return None
    return {
        "year": note.year,
        "calendar": note.calendar,
        "headline": note.headline,
        "what_happened": note.what_happened,
        "what_the_engine_saw": note.what_the_engine_saw,
        "what_the_engine_cannot_see": note.what_the_engine_cannot_see,
    }


def _summary(case: CaseStudy) -> dict:
    """The index-card view: enough to choose a case, not enough to need a run."""
    a = case.underwriting
    return {
        "slug": case.slug,
        "name": case.name,
        "sponsor": case.sponsor,
        "signed": case.signed,
        "closed": case.closed,
        "sector": case.sector,
        "verdict": case.verdict,
        "why_it_is_here": case.why_it_is_here,
        "entry_ev": a.entry_ev,
        "entry_ebitda": a.entry_ebitda,
        "entry_multiple": a.entry_multiple,
        "leverage_turns": a.total_leverage_turns,
        "outcome": _outcome(case),
    }


@app.get("/api/cases")
def cases() -> dict:
    """The library index. No engine runs — the cards are chosen from, not read."""
    return {
        "cases": [_summary(c) for c in CASES],
        "sources": [{"key": s.key, "label": s.label, "url": s.url} for s in SOURCES],
    }


@app.get("/api/cases/{slug}")
def case_detail(slug: str) -> dict:
    """One case, fully replayed.

    Three columns reach the client and they answer three different questions:

    * ``underwriting`` — what this model says about the deal as signed, using
      only information available before close. The no-hindsight verdict.
    * ``realised`` — the same capital structure fed the operating path that
      actually happened. This is the model's own accuracy test: if the engine is
      sound, reality in should give reality out.
    * ``outcome`` — what the deal actually returned, as reported.

    The distance between the first two is the deal's news. The distance between
    the last two is the model's error, and ``model_caveats`` names the
    structural reasons for it rather than tuning an assumption to close the gap.
    """
    case = BY_SLUG.get(slug)
    if case is None:
        raise HTTPException(status_code=404, detail=f"No case study with slug {slug!r}")

    by_key = {s.key: s for s in SOURCES}
    return {
        **_summary(case),
        "thesis": case.thesis,
        "could_not_have_known": case.could_not_have_known,
        "model_caveats": case.model_caveats,
        "column_deltas": _column_deltas(case),
        "provenance": [
            {
                "label": f.label,
                "value": f.value,
                "basis": f.basis,
                "note": f.note,
                "source": (
                    {"key": f.source, "label": by_key[f.source].label, "url": by_key[f.source].url}
                    if f.source in by_key
                    else None
                ),
            }
            for f in case.provenance
        ],
        "sources": [
            {"key": k, "label": by_key[k].label, "url": by_key[k].url}
            for k in case.source_keys
            if k in by_key
        ],
        "underwriting": {
            "assumptions": case.underwriting.model_dump(),
            "note": case.column_notes.get("underwriting"),
            "break_note": _break_note(case, "underwriting"),
            **_replay(case.underwriting),
        },
        "realised": (
            {
                "assumptions": case.realised.model_dump(),
                "note": case.column_notes.get("realised"),
                "break_note": _break_note(case, "realised"),
                **_replay(case.realised),
            }
            if case.realised is not None
            else None
        ),
    }


# ---------------------------------------------------------------- static SPA
#
# In development the SPA is served by Vite and proxies /api here. In production
# there is one process: `npm run build --prefix web` emits web/dist, and this
# app serves it. Mounted last so it can never shadow an /api route.

_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve built files directly; fall back to index.html so client-side
        routes like /simulator survive a hard refresh."""
        candidate = (_DIST / full_path).resolve()
        # Containment check: a crafted path must not escape the dist directory.
        if full_path and _DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")

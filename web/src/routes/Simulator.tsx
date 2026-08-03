/**
 * The simulator.
 *
 * Layout follows the deal tools this imitates: assumptions pinned left, a
 * headline strip that always answers "what's the return and what did it cost",
 * and the evidence organised into tabs below it.
 *
 * The heavier analyses — the sensitivity grid is ~25 engine runs, the tornado
 * 14 — are gated on their tab being open, so dragging a slider on the Overview
 * tab costs exactly one engine run.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  downloadSchedule,
  downloadWorkbook,
  importWorkbook,
  WorkbookInvalid,
  fetchBreakeven,
  fetchDefaults,
  fetchExitProfile,
  fetchScenarios,
  fetchSensitivity,
  fetchTornado,
  runDeal,
} from "../api/client";
import { useDebounced, useEngineQuery } from "../api/hooks";
import type { Assumptions, Defaults } from "../api/types";
import {
  BridgeWaterfall,
  CoverageChart,
  DebtPaydownChart,
  ExitTimingChart,
  LeverageChart,
  OperatingChart,
  TornadoChart,
} from "../components/charts";
import { Heatmap } from "../components/Heatmap";
import { Flags, KpiStrip } from "../components/Kpis";
import { LifecycleTimeline } from "../components/Lifecycle";
import {
  Card,
  Skeleton,
  StructureFailedNotice,
  Tabs,
  type TabDef,
} from "../components/primitives";
import { Sidebar } from "../components/Sidebar";
import {
  BridgeTable,
  CreditTable,
  ScenarioTable,
  ScheduleTable,
  SourcesUsesTable,
} from "../components/tables";
import { fmtMult, fmtPct } from "../lib/format";

const TABS: TabDef[] = [
  { id: "overview", label: "Overview" },
  { id: "risk", label: "Risk & scenarios" },
  { id: "credit", label: "Credit view" },
  { id: "lifecycle", label: "Lifecycle" },
  { id: "schedule", label: "Schedule" },
];

export function Simulator() {
  const [defaults, setDefaults] = useState<Defaults | null>(null);
  const [assumptions, setAssumptions] = useState<Assumptions | null>(null);
  const [tab, setTab] = useState("overview");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [targetIrr, setTargetIrr] = useState(0.2);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchDefaults(controller.signal)
      .then((data) => {
        setDefaults(data);
        setAssumptions(data.assumptions);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setBootError(
          error instanceof Error ? error.message : "Could not reach the engine.",
        );
      });
    return () => controller.abort();
  }, []);

  if (bootError) {
    return (
      <main className="main">
        <div className="callout">
          <strong>The engine isn't responding.</strong> {bootError} Start the API with{" "}
          <code>uvicorn api.main:app --reload</code> and reload this page.
        </div>
      </main>
    );
  }

  if (!defaults || !assumptions) {
    return (
      <main className="main">
        <Skeleton height={92} />
      </main>
    );
  }

  return (
    <SimulatorBody
      defaults={defaults}
      assumptions={assumptions}
      setAssumptions={setAssumptions}
      tab={tab}
      setTab={setTab}
      sidebarOpen={sidebarOpen}
      setSidebarOpen={setSidebarOpen}
      targetIrr={targetIrr}
      setTargetIrr={setTargetIrr}
    />
  );
}

function SimulatorBody({
  defaults,
  assumptions,
  setAssumptions,
  tab,
  setTab,
  sidebarOpen,
  setSidebarOpen,
  targetIrr,
  setTargetIrr,
}: {
  defaults: Defaults;
  assumptions: Assumptions;
  setAssumptions: (a: Assumptions) => void;
  tab: string;
  setTab: (id: string) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  targetIrr: number;
  setTargetIrr: (v: number) => void;
}) {
  // Sliders fire continuously; let the value settle before asking the engine.
  const settled = useDebounced(assumptions, 200);
  // Surfaced inline rather than swallowed: the Excel export refuses deals with
  // capital events it cannot model, and that reason is worth reading.
  const [exportError, setExportError] = useState<string | null>(null);
  // Problems from an uploaded workbook, listed with their cells. Someone
  // fixing a spreadsheet wants every mistake at once, not one per attempt.
  const [importProblems, setImportProblems] = useState<string[]>([]);

  const run = useEngineQuery(settled, useCallback((a, signal) => runDeal(a, signal), []));
  const sensitivity = useEngineQuery(
    settled,
    useCallback((a, signal) => fetchSensitivity(a, signal), []),
    tab === "risk",
  );
  const tornado = useEngineQuery(
    settled,
    useCallback((a, signal) => fetchTornado(a, signal), []),
    tab === "risk",
  );
  const scenarios = useEngineQuery(
    settled,
    useCallback((a, signal) => fetchScenarios(a, signal), []),
    tab === "risk",
  );
  const exitProfile = useEngineQuery(
    settled,
    useCallback((a, signal) => fetchExitProfile(a, signal), []),
    tab === "overview",
  );

  // The breakeven solver depends on the target as well as the deal, so its
  // input is the pair — otherwise changing the target alone wouldn't re-solve.
  const breakevenInput = useMemo(
    () => ({ assumptions: settled, targetIrr }),
    [settled, targetIrr],
  );
  const breakeven = useEngineQuery(
    breakevenInput,
    useCallback(
      (input: { assumptions: Assumptions; targetIrr: number }, signal: AbortSignal) =>
        fetchBreakeven(input.assumptions, input.targetIrr, signal),
      [],
    ),
    tab === "risk",
  );

  const dim = (loading: boolean) => (loading ? "pending" : undefined);

  return (
    <div className={`sim${sidebarOpen ? "" : " collapsed"}`}>
      <aside className="sidebar">
        <div className="sidebar-head">
          <span className="eyebrow">Assumptions</span>
          <button
            className="collapse-btn"
            style={{ marginLeft: "auto" }}
            onClick={() => setSidebarOpen(false)}
            aria-label="Hide the assumptions panel"
            title="Hide the assumptions panel"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <path d="M7.5 2L3.5 6l4 4" fill="none" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          </button>
        </div>
        <Sidebar
          assumptions={assumptions}
          onChange={setAssumptions}
          onReset={() => setAssumptions(defaults.assumptions)}
          presets={defaults.presets}
          benchmarks={defaults.benchmarks}
        />
      </aside>

      <main className="main">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--s3)",
            marginBottom: "var(--s4)",
          }}
        >
          {/* Always present and always labelled — never a chevron that vanishes
              into the background when the panel is closed. */}
          {!sidebarOpen && (
            <button className="btn" onClick={() => setSidebarOpen(true)}>
              ☰ Assumptions
            </button>
          )}
          <span className="eyebrow">All figures in $m unless marked</span>
          {/* The workbook first, because it is the one worth having: a live
              model an analyst can audit and flex, rather than a record of one. */}
          <button
            className="btn btn-primary"
            style={{ marginLeft: "auto" }}
            title="A live model — formulas, blue inputs as named ranges, iterative calculation already switched on"
            onClick={() =>
              void downloadWorkbook(assumptions).catch((e: unknown) =>
                setExportError(e instanceof Error ? e.message : "Export failed."),
              )
            }
          >
            Export live model (Excel)
          </button>
          <label className="btn" style={{ cursor: "pointer" }}
                 title="Bring back a workbook you have been working in — assumptions are read from the named ranges">
            Import workbook
            <input
              type="file"
              accept=".xlsx"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";           // so re-picking the same file fires again
                if (!file) return;
                setImportProblems([]);
                setExportError(null);
                void importWorkbook(file)
                  .then(setAssumptions)
                  .catch((err: unknown) => {
                    if (err instanceof WorkbookInvalid && err.problems.length) {
                      setImportProblems(err.problems.map((p) => p.message));
                    } else {
                      setImportProblems([
                        err instanceof Error ? err.message : "That workbook could not be read.",
                      ]);
                    }
                  });
              }}
            />
          </label>
          <button className="btn" onClick={() => void downloadSchedule(assumptions)}>
            Schedule (CSV)
          </button>
        </div>

        {exportError && <div className="callout">{exportError}</div>}
        {importProblems.length > 0 && (
          <div className="callout">
            <strong>This workbook could not be read.</strong>
            <ul style={{ margin: "var(--s2) 0 0", paddingLeft: "var(--s5)" }}>
              {importProblems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        {run.structureFailed && run.error && <StructureFailedNotice message={run.error} />}
        {run.error && !run.structureFailed && (
          <div className="callout">
            <strong>Could not run the model.</strong> {run.error}
          </div>
        )}

        {run.data && (
          <div className={dim(run.loading)}>
            <KpiStrip run={run.data} />
            <Flags flags={run.data.flags} />
          </div>
        )}

        <Tabs tabs={TABS} active={tab} onChange={setTab} />

        {/* ------------------------------------------------------ overview */}
        {tab === "overview" && (
          <div className="tab-panel">
            {!run.data ? (
              <Skeleton />
            ) : (
              <div className={dim(run.loading)}>
                <Card
                  title="Sources & uses"
                  eyebrow="At close"
                  note="Cash-free / debt-free: the buyer purchases the enterprise, existing debt is refinanced, and sponsor equity is the plug — whatever the debt doesn't cover."
                >
                  <SourcesUsesTable
                    run={run.data}
                    entryEbitda={assumptions.entry_ebitda}
                  />
                </Card>

                <Card
                  title="Operating case"
                  eyebrow="The foundation"
                  note="Revenue and EBITDA with the margin path overlaid. Everything downstream rests on this, so it is worth checking before reading a single return."
                >
                  <OperatingChart run={run.data} />
                </Card>

                <div className="grid-2">
                  <Card
                    title="Value-creation bridge"
                    note="Where the equity gain came from. The four drivers sum exactly to the gain — the reconciliation is shown, not asserted."
                  >
                    <BridgeWaterfall bridge={run.data.bridge} />
                    <BridgeTable run={run.data} />
                  </Card>

                  <Card
                    title="Deleveraging"
                    note="The capital structure over the hold. Cash is drawn separately because it offsets debt without repaying it — the gap between gross and net leverage."
                  >
                    <DebtPaydownChart run={run.data} />
                  </Card>
                </div>

                <Card
                  title="When to sell"
                  eyebrow="Exit timing"
                  note="IRR and MOIC if the sponsor exited at the end of each year instead of the assumed hold, exit multiple unchanged. MOIC compounds with every year of deleveraging while IRR is annualised away — the hold-longer-versus-flip tension, made visible."
                >
                  {exitProfile.data ? (
                    <div className={dim(exitProfile.loading)}>
                      <ExitTimingChart years={exitProfile.data.years} />
                    </div>
                  ) : (
                    <Skeleton height={300} />
                  )}
                </Card>
              </div>
            )}
          </div>
        )}

        {/* ---------------------------------------------------------- risk */}
        {tab === "risk" && (
          <div className="tab-panel">
            <Card
              title="What actually moves the answer"
              eyebrow="Tornado"
              note="Each driver swung one at a time, everything else held at base, ranked by the width of the IRR span. Swings are sized as comparable real-world uncertainties rather than equal percentages, so the ranking means something."
            >
              {tornado.data && run.data ? (
                <div className={dim(tornado.loading)}>
                  <TornadoChart drivers={tornado.data.drivers} baseIrr={run.data.irr} />
                </div>
              ) : (
                <Skeleton height={300} />
              )}
            </Card>

            <Card
              title="Scenarios"
              eyebrow="The IC set"
              note={
                <>
                  Base, upside, downside and a V-shaped recession stress. Note the asymmetry
                  the model surfaces: a sharp shock the business recovers from can beat a
                  permanent downgrade, because the recession leaves terminal EBITDA intact
                  and only hits the exit multiple, while the downside case compounds a lower
                  growth and margin all the way into the exit year.
                </>
              }
            >
              {scenarios.data ? (
                <div className={dim(scenarios.loading)}>
                  <ScenarioTable scenarios={scenarios.data.scenarios} />
                </div>
              ) : (
                <Skeleton height={200} />
              )}
            </Card>

            <Card
              title="The model in reverse"
              eyebrow="Breakeven"
              note="Name a target return and the engine bisects for the exit multiple that clears it. The gap between that and your entry multiple is the honest question: how much of the return are you asking the market to hand you?"
            >
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: "var(--s5)",
                }}
              >
                <label className="field" style={{ minWidth: 260 }}>
                  <span className="field-top">
                    <span className="field-label">Target IRR</span>
                    <span className="field-value">{fmtPct(targetIrr, 0)}</span>
                  </span>
                  <span className="slider-wrap">
                    <input
                      type="range"
                      min={0.05}
                      max={0.5}
                      step={0.01}
                      value={targetIrr}
                      onChange={(event) => setTargetIrr(Number(event.target.value))}
                    />
                  </span>
                </label>

                {breakeven.data && (
                  <div className={dim(breakeven.loading)} style={{ display: "flex", gap: "var(--s6)" }}>
                    <Figure
                      k="Required exit multiple"
                      v={fmtMult(breakeven.data.breakeven_exit_multiple, 2)}
                      sub={
                        breakeven.data.reachable
                          ? `vs. ${fmtMult(breakeven.data.assumed_exit_multiple)} assumed`
                          : "unreachable below 40×"
                      }
                    />
                    <Figure
                      k="Expansion required"
                      v={fmtMult(breakeven.data.expansion_required, 2)}
                      sub={`from a ${fmtMult(breakeven.data.entry_multiple)} entry`}
                    />
                  </div>
                )}
              </div>
            </Card>

            <Card
              title="Entry versus exit"
              eyebrow="Sensitivity"
              note="IRR across a grid of entry and exit multiples. Changing the entry multiple re-levers the deal — debt is sized in turns of EBITDA, so a richer price means a bigger equity cheque, not more debt. Cells where no financeable structure exists are left empty rather than filled with a number."
            >
              {sensitivity.data ? (
                <div className={dim(sensitivity.loading)}>
                  <Heatmap
                    data={sensitivity.data}
                    entryMultiple={assumptions.entry_multiple}
                    exitMultiple={assumptions.exit_multiple}
                  />
                </div>
              ) : (
                <Skeleton height={280} />
              )}
            </Card>
          </div>
        )}

        {/* -------------------------------------------------------- credit */}
        {tab === "credit" && (
          <div className="tab-panel">
            {!run.data ? (
              <Skeleton />
            ) : (
              <div className={dim(run.loading)}>
                <Card
                  title="The lender's view"
                  eyebrow="Credit"
                  note="The covenant-style ratios a credit committee watches. A structure that breaches these on paper doesn't get financed on these terms, however good the equity return looks."
                >
                  <div className="grid-2">
                    <div>
                      <span className="eyebrow">Net leverage</span>
                      <LeverageChart credit={run.data.credit} />
                    </div>
                    <div>
                      <span className="eyebrow">Interest coverage</span>
                      <CoverageChart credit={run.data.credit} />
                    </div>
                  </div>
                  <div style={{ marginTop: "var(--s5)" }}>
                    <CreditTable credit={run.data.credit} />
                  </div>
                </Card>
              </div>
            )}
          </div>
        )}

        {/* ----------------------------------------------------- lifecycle */}
        {tab === "lifecycle" && (
          <div className="tab-panel">
            {!run.data ? (
              <Skeleton />
            ) : (
              <div className={dim(run.loading)}>
                <Card
                  title="Lifetime of the investment"
                  eyebrow="Close to exit"
                  note="The same run read as a sequence of moments rather than a table of years: the cheque, the decisions taken under pressure, the constraints that started to bite, and the exit. Change the structure in the panel and watch which events appear — electing a PIK toggle, drawing the revolver, coverage falling through 2.0×."
                >
                  <LifecycleTimeline
                    events={run.data.lifecycle}
                    holdYears={settled.hold_years}
                  />
                </Card>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------ schedule */}
        {tab === "schedule" && (
          <div className="tab-panel">
            {!run.data ? (
              <Skeleton />
            ) : (
              <div className={dim(run.loading)}>
                <Card
                  title="Annual schedule"
                  eyebrow="Full detail"
                  note="Line items down, years across — the orientation the model would take in Excel. Nothing is summarised away: the NOL roll-forward, the undrawn commitment fee, and the number of passes the interest solve needed are all here."
                >
                  <ScheduleTable run={run.data} />
                </Card>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Figure({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <div className="eyebrow">{k}</div>
      <div
        className="num"
        style={{ fontSize: "1.72rem", color: "var(--pine)", lineHeight: 1.25 }}
      >
        {v}
      </div>
      {sub && (
        <div className="mute" style={{ fontSize: "0.82rem" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

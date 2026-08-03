/**
 * API client.
 *
 * Every call is abortable, because assumptions change on every slider drag and
 * a stale response arriving after a fresh one would show the user the wrong
 * deal. The hooks below always abort the in-flight request before issuing the
 * next, so the last request to *start* is always the one that renders.
 */

import type {
  Assumptions,
  BreakevenResult,
  Defaults,
  ExitProfileYear,
  RunResult,
  Scenario,
  SensitivityResult,
  TornadoDriver,
} from "./types";

/** A structure the engine refuses to model — surfaced as a finding, not a crash. */
export class StructureFailure extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StructureFailure";
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (response.status === 422) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    if (detail?.kind === "structure_failure") {
      throw new StructureFailure(detail.message);
    }
    // Pydantic validation errors land here too; show the first one plainly.
    const first = Array.isArray(detail) ? detail[0] : null;
    throw new Error(
      first ? `${first.loc?.slice(1).join(".")}: ${first.msg}` : "Invalid assumptions.",
    );
  }
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export async function fetchDefaults(signal?: AbortSignal): Promise<Defaults> {
  const response = await fetch("/api/defaults", { signal });
  if (!response.ok) throw new Error("Could not load defaults.");
  return response.json();
}

export const runDeal = (assumptions: Assumptions, signal?: AbortSignal) =>
  post<RunResult>("/api/run", { assumptions }, signal);

export const fetchSensitivity = (assumptions: Assumptions, signal?: AbortSignal) =>
  post<SensitivityResult>("/api/sensitivity", { assumptions }, signal);

export const fetchTornado = (assumptions: Assumptions, signal?: AbortSignal) =>
  post<{ drivers: TornadoDriver[] }>("/api/tornado", { assumptions }, signal);

export const fetchScenarios = (assumptions: Assumptions, signal?: AbortSignal) =>
  post<{ scenarios: Scenario[] }>("/api/scenarios", { assumptions }, signal);

export const fetchExitProfile = (assumptions: Assumptions, signal?: AbortSignal) =>
  post<{ years: ExitProfileYear[] }>("/api/exit-profile", { assumptions }, signal);

export const fetchBreakeven = (
  assumptions: Assumptions,
  targetIrr: number,
  signal?: AbortSignal,
) => post<BreakevenResult>("/api/breakeven", { assumptions, target_irr: targetIrr }, signal);

/** One thing wrong with an uploaded workbook, located precisely enough to fix. */
export interface WorkbookProblem {
  field: string;
  cell: string | null;
  message: string;
}

export class WorkbookInvalid extends Error {
  constructor(message: string, readonly problems: WorkbookProblem[]) {
    super(message);
    this.name = "WorkbookInvalid";
  }
}

/** Read a deal back out of a workbook the analyst has been working in. */
export async function importWorkbook(file: File): Promise<Assumptions> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/import.xlsx", { method: "POST", body });

  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new WorkbookInvalid(
      detail?.message ?? "That workbook could not be read.",
      detail?.problems ?? [],
    );
  }
  return (await response.json()).assumptions as Assumptions;
}

/** The live Excel model: formulas, named ranges, iterative calculation on.
 *  Unlike the CSV this is a working model, not a record of one. */
export async function downloadWorkbook(assumptions: Assumptions): Promise<void> {
  const response = await fetch("/api/model.xlsx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assumptions }),
  });
  if (response.status === 422) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(detail?.message ?? "This deal cannot be exported to Excel.");
  }
  if (!response.ok) throw new Error("Could not build the workbook.");
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "lbo-model.xlsx";
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Streams the annual schedule to a file the reviewer can check in Excel. */
export async function downloadSchedule(assumptions: Assumptions): Promise<void> {
  const response = await fetch("/api/schedule.csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assumptions }),
  });
  if (!response.ok) throw new Error("Could not export the schedule.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "lbo-schedule.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

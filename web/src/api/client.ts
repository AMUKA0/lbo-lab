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

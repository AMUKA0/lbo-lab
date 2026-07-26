/**
 * The case-study library: wire types and fetchers.
 *
 * The shape here mirrors `api/case_studies.py` deliberately closely, because the
 * whole value of the feature is that a reader can trace any number on screen
 * back to a sourced input. Flattening the provenance into prose on the client
 * would break that chain.
 *
 * Note that a *failed* column is a normal, expected response — not an error.
 * Two of the four cases in the library are supposed to fail, and one of them
 * fails on its own underwriting. `CaseColumn.failed` carries that; there is no
 * exception to catch.
 */

import type { Assumptions, RunResult } from "./types";

export type Basis = "reported" | "derived" | "estimated";
export type Verdict = "home run" | "solid" | "flat" | "wipeout";

export interface SourceRef {
  key: string;
  label: string;
  url: string;
}

export interface Figure {
  label: string;
  value: string;
  basis: Basis;
  note: string;
  source: SourceRef | null;
}

export interface CaseOutcome {
  exit_route: string;
  exit_year: number;
  holding_years: number;
  /** null where the sponsor was wiped out and a multiple is meaningless. */
  realised_moic: number | null;
  realised_irr: number | null;
  confidence: "reported" | "widely reported" | "estimated" | "disputed";
  headline: string;
  narrative: string;
}

export interface CaseSummary {
  slug: string;
  name: string;
  sponsor: string;
  signed: string;
  closed: string;
  sector: string;
  verdict: Verdict;
  why_it_is_here: string;
  entry_ev: number;
  entry_ebitda: number;
  entry_multiple: number;
  leverage_turns: number;
  outcome: CaseOutcome;
}

export interface CaseColumn {
  assumptions: Assumptions;
  /** Read before the numbers: what this column means, where it needs interpreting. */
  note: string | null;
  failed: boolean;
  message: string | null;
  irr: number | null;
  moic: number | null;
  wiped_out?: boolean;
  run: RunResult | null;
}

export interface CaseDetail extends CaseSummary {
  thesis: string;
  could_not_have_known: string;
  model_caveats: string[];
  provenance: Figure[];
  sources: SourceRef[];
  underwriting: CaseColumn;
  realised: CaseColumn | null;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (response.status === 404) throw new Error("No such case study.");
  if (!response.ok) throw new Error(`Request failed (${response.status}).`);
  return response.json() as Promise<T>;
}

export const fetchCases = (signal?: AbortSignal) =>
  get<{ cases: CaseSummary[]; sources: SourceRef[] }>("/api/cases", signal);

export const fetchCase = (slug: string, signal?: AbortSignal) =>
  get<CaseDetail>(`/api/cases/${slug}`, signal);

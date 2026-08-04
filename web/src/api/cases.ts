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

/** An account of the year a column runs out of liquidity. Three separate
 *  claims, kept apart on purpose: what actually happened, what the engine
 *  computed, and what the engine structurally could not see — the third being
 *  why the modelled break and the real outcome differ. */
export interface BreakNote {
  year: number;
  calendar: string;
  headline: string;
  what_happened: string;
  what_the_engine_saw: string;
  what_the_engine_cannot_see: string;
}

export interface CaseColumn {
  assumptions: Assumptions;
  /** Read before the numbers: what this column means, where it needs interpreting. */
  note: string | null;
  /** Present only where this column breaks. */
  break_note: BreakNote | null;
  failed: boolean;
  /** WHICH wall was hit. "Runs out of cash", "breaches its leverage covenant
   *  while still paying every coupon", and "cannot refinance a maturity" are
   *  three different findings with three different remedies. */
  failure_kind: "liquidity" | "covenant" | "maturity" | null;
  message: string | null;
  /** The year the structure breaks, when it does. */
  breaks_in_year: number | null;
  /** How many years it serviced itself before that. */
  survived_years: number;
  irr: number | null;
  moic: number | null;
  wiped_out?: boolean;
  run: RunResult | null;
  /** The schedule for the years it *did* survive. Present only on a break, and
   *  deliberately carrying no IRR or MOIC — there was no exit in that year, and
   *  printing a return for one would be an invention. */
  partial_run: RunResult | null;
}

/** An input that differs between the two columns. Surfaced because "same
 *  structure, fed the operating path" is only worth something if the reader can
 *  see what else moved. */
/** Why the modelled equity cheque is not the one the sponsors wrote. Every case
 *  models a larger one, because the reported enterprise value already nets to
 *  the reported equity and this model puts fees and funded cash into Uses on
 *  top. Correct in itself, and previously disclosed on one case out of five. */
export interface EquityReconciliation {
  reported: number;
  modelled: number;
  difference: number;
  pct: number;
  components: { label: string; value: number }[];
  /** What the components do not account for. Shown, because a reconciliation
   *  that does not reconcile is worse than none. */
  unexplained: number;
  moic_modelled: number | null;
  /** The like-for-like figure: the multiple on the cheque actually written. */
  moic_on_reported: number | null;
}

export interface ColumnDelta {
  field: string;
  underwriting: string;
  realised: string;
}

export interface CaseDetail extends CaseSummary {
  thesis: string;
  could_not_have_known: string;
  model_caveats: string[];
  column_deltas: ColumnDelta[];
  equity_reconciliation: EquityReconciliation | null;
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

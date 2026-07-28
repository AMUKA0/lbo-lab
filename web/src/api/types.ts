/**
 * Wire types, mirroring `api/serialisation.py` field for field.
 *
 * `null` is meaningful throughout and is never coerced to zero: the engine
 * produces NaN for a structure that fails or a sponsor that is wiped out, and
 * infinity for coverage with no interest. Both serialise to null, and the UI
 * renders null as "n/a". A fabricated number in a sensitivity grid is worse
 * than an empty cell, because it looks like an answer.
 */

export interface DebtTranche {
  name: string;
  leverage_turns: number;
  cash_rate: number;
  pik_rate: number;
  mandatory_amort_pct: number;
  sweepable: boolean;
  /** Issuer may elect to PIK this coupon when cash is short — the defining
   *  structural feature of 2006–07 vintage credit. */
  pik_toggle: boolean;
  pik_toggle_premium: number;
}

export interface RevolverAssumptions {
  commitment: number;
  cash_rate: number;
  undrawn_fee: number;
}

export interface OperatingAssumptions {
  entry_revenue: number;
  revenue_growth: number | number[];
  ebitda_margin: number | number[];
  da_pct_revenue: number;
  capex_pct_revenue: number;
  nwc_pct_revenue: number;
  tax_rate: number;
}

/** A dividend recapitalisation. Sized EITHER by a target leverage — the way a
 *  sponsor actually instructs one — or by a fixed amount; the engine rejects a
 *  payload carrying both or neither. */
export interface DividendRecap {
  year: number;
  target_leverage_turns: number | null;
  amount: number | null;
  /** Tranche the new debt joins; null defaults to the most senior. */
  tranche: string | null;
  financing_fee_pct: number;
}

/** Follow-on sponsor capital. One shape covers a straight equity cure, a debt
 *  repurchase below par, and a debt-for-equity conversion. */
export interface EquityInjection {
  year: number;
  amount: number;
  debt_retired: number;
  label: string;
}

export interface Assumptions {
  entry_ebitda: number;
  entry_multiple: number;
  operating: OperatingAssumptions;
  tranches: DebtTranche[];
  revolver: RevolverAssumptions;
  recaps: DividendRecap[];
  injections: EquityInjection[];
  transaction_fee_pct_ev: number;
  financing_fee_pct_debt: number;
  financing_fee_tenor_years: number;
  exit_fee_pct_ev: number;
  nol_limit_pct: number;
  interest_on_average_balance: boolean;
  minimum_cash: number;
  cash_sweep_pct: number;
  hold_years: number;
  exit_multiple: number;
}

export interface TrancheYear {
  name: string;
  opening: number;
  cash_interest: number;
  pik_accrual: number;
  mandatory_repayment: number;
  sweep_repayment: number;
  closing: number;
  pik_elected: boolean;
}

/** One moment in the hold — a decision taken or a constraint biting. Derived
 *  from the run rather than computed anew. */
export interface LifecycleEvent {
  year: number;
  kind:
    | "entry"
    | "pik_toggle"
    | "recap"
    | "recap_unfunded"
    | "injection"
    | "divestiture"
    | "revolver"
    | "coverage"
    | "leverage"
    | "exit";
  title: string;
  detail: string;
  tone: "neutral" | "good" | "watch" | "bad";
}

export interface YearRow {
  year: number;
  revenue: number;
  ebitda: number;
  ebitda_margin: number;
  da: number;
  ebit: number;
  capex: number;
  delta_nwc: number;
  fee_amortisation: number;
  cash_interest_total: number;
  pik_accrual_total: number;
  revolver_undrawn_fee: number;
  ebt: number;
  nol_opening: number;
  nol_used: number;
  nol_closing: number;
  taxes: number;
  net_income: number;
  cash_available_for_debt_service: number;
  revolver_opening: number;
  revolver_draw: number;
  revolver_repayment: number;
  revolver_closing: number;
  opening_cash: number;
  closing_cash: number;
  total_debt_closing: number;
  net_debt_closing: number;
  /** Dividend recap in this year, if any. `raised` is gross incremental debt;
   *  `dividend` is what reached the sponsor after the financing fee. A target
   *  above current leverage leaves `raised` at zero — the recap was not
   *  fundable, which is reported rather than hidden. */
  pik_elections: string[];
  equity_injected: number;
  debt_retired: number;
  recap_target: number;
  recap_raised: number;
  recap_fee: number;
  recap_dividend: number;
  interest_iterations: number;
  tranches: TrancheYear[];
}

export interface SourcesUses {
  entry_ev: number;
  transaction_fees: number;
  financing_fees: number;
  cash_to_balance_sheet: number;
  total_uses: number;
  tranche_amounts: Record<string, number>;
  total_debt: number;
  sponsor_equity: number;
  total_sources: number;
}

export interface Bridge {
  ebitda_growth: number;
  multiple_expansion: number;
  deleveraging: number;
  /** GROSS incremental debt raised in recaps — not the net dividend. The net
   *  would leave the identity short by exactly the financing fee. */
  recapitalisation: number;
  /** Negative by construction: capital the sponsor had to put in, offsetting the
   *  deleveraging it bought. */
  follow_on_equity: number;
  fee_drag: number;
  entry_equity: number;
  exit_equity: number;
  dividends: number;
  /** Entry cheque plus any rescue capital — the denominator MOIC is struck on. */
  total_invested: number;
  /** Exit equity plus recap dividends: what the sponsor actually got back. */
  total_proceeds: number;
  total_value_created: number;
  equity_gain: number;
  /** Asserted to be zero by the test suite; surfaced so the UI can prove it. */
  reconciliation_error: number;
}

export type FlagLevel = "amber" | "info";

export interface Flag {
  field: string;
  level: FlagLevel;
  message: string;
  source: string;
}

export interface CreditYear {
  year: number;
  net_leverage: number | null;
  interest_coverage: number | null;
  /** Cash interest plus PIK accrual — what the lenders are owed for the year,
   *  paid or not. Diverges from the cash figure wherever a PIK strip compounds. */
  total_interest_coverage: number | null;
  ebitda_less_capex_coverage: number | null;
  fcf_conversion: number | null;
}

export interface RunResult {
  sources_uses: SourcesUses;
  years: YearRow[];
  tranche_names: string[];
  exit_ebitda: number;
  exit_ev: number;
  exit_net_debt: number;
  exit_fees: number;
  exit_equity: number;
  entry_equity: number;
  entry_net_debt: number;
  entry_net_leverage: number | null;
  exit_net_leverage: number | null;
  moic: number | null;
  irr: number | null;
  equity_cash_flows: number[];
  bridge: Bridge;
  lifecycle: LifecycleEvent[];
  credit: CreditYear[];
  flags: Flag[];
  wiped_out: boolean;
}

export interface SensitivityResult {
  entry_multiples: number[];
  exit_multiples: number[];
  /** Row-major: values[i][j] is entry_multiples[i] × exit_multiples[j]. */
  values: (number | null)[][];
}

export interface TornadoDriver {
  driver: string;
  low_irr: number | null;
  high_irr: number | null;
  base_irr: number | null;
}

export interface Scenario {
  name: string;
  failed: boolean;
  message: string | null;
  irr: number | null;
  moic: number | null;
  entry_equity: number | null;
  exit_equity: number | null;
  exit_ebitda: number | null;
  exit_multiple: number;
  exit_net_leverage: number | null;
  min_interest_coverage: number | null;
  wiped_out: boolean;
}

export interface ExitProfileYear {
  exit_year: number;
  irr: number | null;
  moic: number | null;
}

export interface BreakevenResult {
  target_irr: number;
  breakeven_exit_multiple: number | null;
  entry_multiple: number;
  assumed_exit_multiple: number;
  expansion_required: number | null;
  reachable: boolean;
}

export interface Benchmark {
  band: [number, number];
  note: string;
  source: string;
}

export interface Preset {
  name: string;
  blurb: string;
  assumptions: Assumptions;
}

export interface Defaults {
  assumptions: Assumptions;
  presets: Preset[];
  benchmarks: Record<string, Benchmark>;
}

/**
 * The assumptions panel.
 *
 * Every field the engine accepts is editable here — nothing is hidden behind a
 * "simple mode". That includes the ones a lighter tool would bury: the facility
 * tenor over which financing fees amortise, the NOL shelter limit, and the
 * circularity convention itself.
 *
 * Two things go beyond what a form strictly needs:
 *
 * - **Per-year schedules.** Growth and margin can each be switched from a flat
 *   rate to a year-by-year path, because a real operating case is rarely a
 *   straight line and a V-shaped one behaves very differently from its average.
 * - **Dynamic tranches.** The capital structure is a list, not a fixed senior
 *   and mezz. Unitranche, second lien, a PIK toggle — the engine already
 *   supports any stack, so the UI should too.
 */

import type { Assumptions, Benchmark, DebtTranche, Preset } from "../api/types";
import { fmtMoney, fmtMult, fmtPct } from "../lib/format";
import { Group, NumberField, SliderField, ToggleField } from "./primitives";

type Patch = (next: Assumptions) => void;

const clone = (a: Assumptions): Assumptions => JSON.parse(JSON.stringify(a)) as Assumptions;

/** Grow or trim a per-year schedule when the hold period changes, holding the
 *  last value for new years — the engine rejects a mismatched length. */
function resize(schedule: number | number[], years: number): number | number[] {
  if (!Array.isArray(schedule)) return schedule;
  const out = schedule.slice(0, years);
  while (out.length < years) out.push(out[out.length - 1] ?? 0);
  return out;
}

export function Sidebar({
  assumptions,
  onChange,
  onReset,
  presets,
  benchmarks,
}: {
  assumptions: Assumptions;
  onChange: (next: Assumptions) => void;
  onReset: () => void;
  presets: Preset[];
  benchmarks: Record<string, Benchmark>;
}) {
  const a = assumptions;
  const edit = (mutate: Patch) => {
    const next = clone(a);
    mutate(next);
    onChange(next);
  };

  const band = (key: string): [number, number] | undefined => {
    const b = benchmarks[key];
    return b ? [b.band[0], b.band[1]] : undefined;
  };

  const totalTurns = a.tranches.reduce((sum, t) => sum + t.leverage_turns, 0);

  return (
    <div className="sidebar-body">
      <Group title="Preset structures" defaultOpen>
        <div className="chip-row">
          {presets.map((preset) => (
            <button
              key={preset.name}
              className="chip"
              title={preset.blurb}
              onClick={() => onChange(clone(preset.assumptions))}
            >
              {preset.name}
            </button>
          ))}
          <button className="chip" onClick={onReset}>
            Reset
          </button>
        </div>
      </Group>

      {/* ------------------------------------------------------------ entry */}
      <Group title="Entry" defaultOpen>
        <NumberField
          label="Entry EBITDA"
          value={a.entry_ebitda}
          min={1}
          step={5}
          suffix="$m"
          onChange={(v) => edit((n) => (n.entry_ebitda = v))}
        />
        <SliderField
          label="Entry multiple"
          value={a.entry_multiple}
          min={4}
          max={20}
          step={0.25}
          band={band("entry_multiple")}
          format={(v) => fmtMult(v)}
          onChange={(v) => edit((n) => (n.entry_multiple = v))}
          note={`Enterprise value ${fmtMoney(a.entry_ebitda * a.entry_multiple)}. The shaded band is the typical market range.`}
        />
        <NumberField
          label="Entry revenue"
          value={a.operating.entry_revenue}
          min={1}
          step={10}
          suffix="$m"
          onChange={(v) => edit((n) => (n.operating.entry_revenue = v))}
        />
      </Group>

      {/* ------------------------------------------------------- operations */}
      <Group title="Operating case">
        <ScheduleField
          label="Revenue growth"
          value={a.operating.revenue_growth}
          years={a.hold_years}
          min={-0.2}
          max={0.3}
          step={0.005}
          band={band("revenue_growth")}
          format={(v) => fmtPct(v)}
          onChange={(v) => edit((n) => (n.operating.revenue_growth = v))}
        />
        <ScheduleField
          label="EBITDA margin"
          value={a.operating.ebitda_margin}
          years={a.hold_years}
          min={0.02}
          max={0.6}
          step={0.002}
          format={(v) => fmtPct(v)}
          onChange={(v) => edit((n) => (n.operating.ebitda_margin = v))}
        />
        <SliderField
          label="D&A (% of revenue)"
          value={a.operating.da_pct_revenue}
          min={0}
          max={0.2}
          step={0.002}
          format={(v) => fmtPct(v)}
          onChange={(v) => edit((n) => (n.operating.da_pct_revenue = v))}
        />
        <SliderField
          label="Capex (% of revenue)"
          value={a.operating.capex_pct_revenue}
          min={0}
          max={0.25}
          step={0.002}
          format={(v) => fmtPct(v)}
          onChange={(v) => edit((n) => (n.operating.capex_pct_revenue = v))}
        />
        <SliderField
          label="Working capital (% of revenue)"
          value={a.operating.nwc_pct_revenue}
          min={0}
          max={0.4}
          step={0.005}
          format={(v) => fmtPct(v)}
          onChange={(v) => edit((n) => (n.operating.nwc_pct_revenue = v))}
          note="ΔNWC is this percentage applied to the change in revenue, not to the level."
        />
        <SliderField
          label="Tax rate"
          value={a.operating.tax_rate}
          min={0}
          max={0.5}
          step={0.005}
          format={(v) => fmtPct(v)}
          onChange={(v) => edit((n) => (n.operating.tax_rate = v))}
        />
      </Group>

      {/* ---------------------------------------------------------- tranches */}
      <Group title={`Capital structure — ${fmtMult(totalTurns, 2)} of leverage`} defaultOpen>
        {a.tranches.map((tranche, index) => (
          <TrancheEditor
            key={index}
            tranche={tranche}
            index={index}
            canRemove={a.tranches.length > 1}
            onChange={(mutate) => edit((n) => mutate(n.tranches[index]))}
            onRemove={() => edit((n) => n.tranches.splice(index, 1))}
          />
        ))}
        <button
          className="btn"
          style={{ width: "100%", justifyContent: "center" }}
          onClick={() =>
            edit((n) =>
              n.tranches.push({
                name: `Tranche ${n.tranches.length + 1}`,
                leverage_turns: 1,
                cash_rate: 0.09,
                pik_rate: 0,
                mandatory_amort_pct: 0,
                sweepable: false,
              }),
            )
          }
        >
          + Add tranche
        </button>
      </Group>

      {/* ---------------------------------------------------------- revolver */}
      <Group title="Revolver & cash policy">
        <NumberField
          label="Revolver commitment"
          value={a.revolver.commitment}
          min={0}
          step={10}
          suffix="$m"
          onChange={(v) => edit((n) => (n.revolver.commitment = v))}
        />
        <SliderField
          label="Revolver rate"
          value={a.revolver.cash_rate}
          min={0}
          max={0.2}
          step={0.0025}
          format={(v) => fmtPct(v, 2)}
          onChange={(v) => edit((n) => (n.revolver.cash_rate = v))}
        />
        <SliderField
          label="Undrawn commitment fee"
          value={a.revolver.undrawn_fee}
          min={0}
          max={0.02}
          step={0.00025}
          format={(v) => fmtPct(v, 3)}
          onChange={(v) => edit((n) => (n.revolver.undrawn_fee = v))}
        />
        <NumberField
          label="Minimum operating cash"
          value={a.minimum_cash}
          min={0}
          step={5}
          suffix="$m"
          onChange={(v) => edit((n) => (n.minimum_cash = v))}
        />
        <SliderField
          label="Cash sweep"
          value={a.cash_sweep_pct}
          min={0}
          max={1}
          step={0.05}
          format={(v) => fmtPct(v, 0)}
          onChange={(v) => edit((n) => (n.cash_sweep_pct = v))}
          note="Share of excess cash applied to optional prepayment, senior-first. Credit agreements typically require 50–100%."
        />
      </Group>

      {/* -------------------------------------------------------------- fees */}
      <Group title="Fees">
        <SliderField
          label="Transaction fees (% of EV)"
          value={a.transaction_fee_pct_ev}
          min={0}
          max={0.05}
          step={0.0025}
          format={(v) => fmtPct(v, 2)}
          onChange={(v) => edit((n) => (n.transaction_fee_pct_ev = v))}
        />
        <SliderField
          label="Financing fees (% of debt)"
          value={a.financing_fee_pct_debt}
          min={0}
          max={0.06}
          step={0.0025}
          format={(v) => fmtPct(v, 2)}
          onChange={(v) => edit((n) => (n.financing_fee_pct_debt = v))}
        />
        <SliderField
          label="Facility tenor"
          value={a.financing_fee_tenor_years}
          min={1}
          max={10}
          step={1}
          format={(v) => `${v} yrs`}
          onChange={(v) => edit((n) => (n.financing_fee_tenor_years = v))}
          note="Financing fees amortise over the facility's life (ASC 835-30), not the hold — so on a shorter hold, part of the fee is never expensed pre-exit."
        />
        <SliderField
          label="Exit / sale-process costs (% of EV)"
          value={a.exit_fee_pct_ev}
          min={0}
          max={0.04}
          step={0.0025}
          format={(v) => fmtPct(v, 2)}
          onChange={(v) => edit((n) => (n.exit_fee_pct_ev = v))}
        />
      </Group>

      {/* ------------------------------------------------------- conventions */}
      <Group title="Modelling conventions">
        <ToggleField
          label="Interest on average balances"
          checked={a.interest_on_average_balance}
          onChange={(v) => edit((n) => (n.interest_on_average_balance = v))}
          note={
            a.interest_on_average_balance
              ? "The advanced-model convention. Circular — interest drives the sweep, which drives balances, which drive interest — resolved by an iterative solve each year to a 1e-10 tolerance."
              : "Circularity breaker: interest on opening balances only. Acyclic and single-pass, but it overstates interest. This is the escape hatch bank models ship."
          }
        />
        <SliderField
          label="NOL shelter limit"
          value={a.nol_limit_pct}
          min={0}
          max={1}
          step={0.05}
          format={(v) => fmtPct(v, 0)}
          onChange={(v) => edit((n) => (n.nol_limit_pct = v))}
          note="Losses carry forward and shelter up to this share of a later year's pre-tax income. 80% is the post-TCJA US rule (§172(a)); set to 0% to disable carryforwards entirely."
        />
      </Group>

      {/* -------------------------------------------------------------- exit */}
      <Group title="Exit" defaultOpen>
        <SliderField
          label="Hold period"
          value={a.hold_years}
          min={1}
          max={10}
          step={1}
          band={band("hold_years")}
          format={(v) => `${v} yrs`}
          onChange={(v) =>
            edit((n) => {
              n.hold_years = v;
              // Per-year paths must match the new hold or the engine rejects them.
              n.operating.revenue_growth = resize(n.operating.revenue_growth, v);
              n.operating.ebitda_margin = resize(n.operating.ebitda_margin, v);
            })
          }
        />
        <SliderField
          label="Exit multiple"
          value={a.exit_multiple}
          min={4}
          max={20}
          step={0.25}
          format={(v) => fmtMult(v)}
          onChange={(v) => edit((n) => (n.exit_multiple = v))}
          note={
            a.exit_multiple > a.entry_multiple
              ? `Assumes ${fmtMult(a.exit_multiple - a.entry_multiple, 2)} of multiple expansion — the driver you control least.`
              : a.exit_multiple < a.entry_multiple
                ? `Underwriting ${fmtMult(a.entry_multiple - a.exit_multiple, 2)} of multiple compression.`
                : "Underwritten flat to entry — the disciplined convention."
          }
        />
      </Group>
    </div>
  );
}

/* ------------------------------------------------------------------ tranche */

function TrancheEditor({
  tranche,
  index,
  canRemove,
  onChange,
  onRemove,
}: {
  tranche: DebtTranche;
  index: number;
  canRemove: boolean;
  onChange: (mutate: (t: DebtTranche) => void) => void;
  onRemove: () => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--edge)",
        borderRadius: "var(--radius)",
        padding: "var(--s3)",
        display: "grid",
        gap: "var(--s3)",
        background: "var(--raise)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="eyebrow">{index === 0 ? "Most senior" : `Tranche ${index + 1}`}</span>
        {canRemove && (
          <button
            className="chip"
            style={{ marginLeft: "auto", padding: "2px 8px" }}
            onClick={onRemove}
            aria-label={`Remove ${tranche.name}`}
          >
            Remove
          </button>
        )}
      </div>

      <input
        type="text"
        value={tranche.name}
        aria-label="Tranche name"
        onChange={(event) => onChange((t) => (t.name = event.target.value))}
      />

      <SliderField
        label="Leverage"
        value={tranche.leverage_turns}
        min={0.25}
        max={8}
        step={0.25}
        format={(v) => fmtMult(v, 2)}
        onChange={(v) => onChange((t) => (t.leverage_turns = v))}
      />
      <SliderField
        label="Cash coupon"
        value={tranche.cash_rate}
        min={0}
        max={0.2}
        step={0.0025}
        format={(v) => fmtPct(v, 2)}
        onChange={(v) => onChange((t) => (t.cash_rate = v))}
      />
      <SliderField
        label="PIK rate"
        value={tranche.pik_rate}
        min={0}
        max={0.15}
        step={0.0025}
        format={(v) => fmtPct(v, 2)}
        onChange={(v) => onChange((t) => (t.pik_rate = v))}
      />
      <SliderField
        label="Mandatory amortisation"
        value={tranche.mandatory_amort_pct}
        min={0}
        max={0.25}
        step={0.005}
        format={(v) => fmtPct(v, 1)}
        onChange={(v) => onChange((t) => (t.mandatory_amort_pct = v))}
        note="A percentage of the ORIGINAL principal each year — the term-loan convention, not a percentage of the balance outstanding."
      />
      <ToggleField
        label="Cash sweeps against this tranche"
        checked={tranche.sweepable}
        onChange={(v) => onChange((t) => (t.sweepable = v))}
      />
    </div>
  );
}

/* --------------------------------------------------------- schedule fields */

/**
 * A driver that is either flat across the hold or specified year by year.
 *
 * The flat case is one slider. Switching to a path reveals one slider per year,
 * seeded from the flat value — so you can build a V-shaped recovery, a ramp, or
 * a margin step-up without leaving the panel.
 */
function ScheduleField({
  label,
  value,
  years,
  min,
  max,
  step,
  band,
  format,
  onChange,
}: {
  label: string;
  value: number | number[];
  years: number;
  min: number;
  max: number;
  step: number;
  band?: [number, number];
  format: (v: number) => string;
  onChange: (value: number | number[]) => void;
}) {
  const isPath = Array.isArray(value);
  const flat = isPath ? (value as number[])[0] ?? min : (value as number);
  const path = isPath ? (value as number[]) : Array.from({ length: years }, () => flat);

  return (
    <div style={{ display: "grid", gap: "var(--s2)" }}>
      {!isPath ? (
        <SliderField
          label={label}
          value={flat}
          min={min}
          max={max}
          step={step}
          band={band}
          format={format}
          onChange={(v) => onChange(v)}
        />
      ) : (
        <>
          <span className="field-top">
            <span className="field-label">{label} — by year</span>
          </span>
          {path.slice(0, years).map((v, i) => (
            <SliderField
              key={i}
              label={`Year ${i + 1}`}
              value={v}
              min={min}
              max={max}
              step={step}
              band={band}
              format={format}
              onChange={(next) => {
                const updated = path.slice(0, years);
                updated[i] = next;
                onChange(updated);
              }}
            />
          ))}
        </>
      )}
      <button
        className={`chip${isPath ? " is-on" : ""}`}
        style={{ justifySelf: "start" }}
        aria-pressed={isPath}
        onClick={() => onChange(isPath ? flat : Array.from({ length: years }, () => flat))}
      >
        {isPath ? "Use a flat rate" : "Vary by year"}
      </button>
    </div>
  );
}

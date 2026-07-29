/**
 * Charts.
 *
 * Each one answers a specific question an investment committee would ask, and
 * the caption on the card says which. Nothing here computes anything: every
 * number is already in the API response, so what you see is what the tested
 * engine produced.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  Bridge,
  CreditYear,
  ExitProfileYear,
  RunResult,
  TornadoDriver,
} from "../api/types";
import { fmtMoney, fmtMult, fmtPct, fmtSigned, NA } from "../lib/format";
import { C, CASH_COLOUR, REVOLVER_COLOUR, TRANCHE_COLOURS } from "../lib/palette";

const AXIS = { stroke: C.edge, tickLine: false, axisLine: { stroke: C.edge } };

interface TipRow {
  label: string;
  value: string;
  colour?: string;
}

function Tip({ title, rows }: { title: string; rows: TipRow[] }) {
  return (
    <div className="tooltip">
      <div className="t-title">{title}</div>
      {rows.map((row) => (
        <div className="t-row" key={row.label}>
          <span style={row.colour ? { color: row.colour } : undefined}>{row.label}</span>
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------- value-creation bridge */

/**
 * The waterfall is built as a stacked bar: an invisible `base` lifts each
 * floating step to its starting height, and `span` is the visible magnitude.
 * Entry and exit equity are anchored to zero because they are levels, not
 * movements.
 */
export function BridgeWaterfall({ bridge }: { bridge: Bridge | null }) {
  // No exit, no gain to decompose. Callers pass the bridge straight through,
  // so the null case is handled here rather than at every call site.
  if (!bridge) return null;
  const steps = [
    { name: "Entry equity", delta: bridge.entry_equity, anchor: true },
    { name: "EBITDA growth", delta: bridge.ebitda_growth, anchor: false },
    { name: "Multiple", delta: bridge.multiple_expansion, anchor: false },
    { name: "Debt paydown", delta: bridge.deleveraging, anchor: false },
    ...(bridge.divestitures !== 0
      ? [{ name: "Divestitures", delta: bridge.divestitures, anchor: false }]
      : []),
    // Only drawn when a recap happened, so the common case keeps a five-bar
    // waterfall rather than carrying a permanent zero-height step.
    ...(bridge.recapitalisation !== 0
      ? [{ name: "Recap", delta: bridge.recapitalisation, anchor: false }]
      : []),
    ...(bridge.follow_on_equity !== 0
      ? [{ name: "Sponsor capital", delta: bridge.follow_on_equity, anchor: false }]
      : []),
    { name: "Fees", delta: bridge.fee_drag, anchor: false },
    { name: "Total proceeds", delta: bridge.total_proceeds, anchor: true },
  ];

  let cursor = 0;
  const data = steps.map((step) => {
    if (step.anchor) {
      cursor = step.delta;
      return {
        name: step.name,
        base: 0,
        span: Math.max(step.delta, 0),
        delta: step.delta,
        anchor: true,
      };
    }
    const start = cursor;
    cursor += step.delta;
    return {
      name: step.name,
      base: Math.min(start, cursor),
      span: Math.abs(step.delta),
      delta: step.delta,
      anchor: false,
    };
  });

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="name" {...AXIS} interval={0} />
        <YAxis {...AXIS} tickFormatter={(v) => fmtMoney(v)} width={72} />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.03)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as (typeof data)[number];
            return (
              <Tip
                title={row.name}
                rows={[
                  {
                    label: row.anchor ? "Level" : "Contribution",
                    value: row.anchor ? fmtMoney(row.delta) : fmtSigned(row.delta),
                  },
                ]}
              />
            );
          }}
        />
        <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="span" stackId="w" radius={[2, 2, 0, 0]} animationDuration={480}>
          {data.map((row, index) => (
            <Cell
              key={index}
              fill={row.anchor ? C.text2 : row.delta >= 0 ? C.pine : C.rust}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* --------------------------------------------------------------- debt paydown */

/**
 * The capital structure over the hold, including year 0 at close. Cash is drawn
 * as a separate band because it offsets debt without repaying it — the gap
 * between gross and net leverage made visual.
 */
export function DebtPaydownChart({ run }: { run: RunResult }) {
  const su = run.sources_uses;
  const data = [
    {
      year: 0,
      cash: su.cash_to_balance_sheet,
      revolver: 0,
      ...su.tranche_amounts,
    } as Record<string, number>,
    ...run.years.map((y) => {
      const row: Record<string, number> = {
        year: y.year,
        cash: y.closing_cash,
        revolver: y.revolver_closing,
      };
      y.tranches.forEach((t) => {
        row[t.name] = t.closing;
      });
      return row;
    }),
  ];

  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="year" {...AXIS} tickFormatter={(v) => (v === 0 ? "Close" : `Y${v}`)} />
        <YAxis {...AXIS} tickFormatter={(v) => fmtMoney(v)} width={72} />
        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            return (
              <Tip
                title={label === 0 ? "At close" : `Year ${label}`}
                rows={payload
                  .slice()
                  .reverse()
                  .map((item) => ({
                    label: String(item.name),
                    value: fmtMoney(item.value as number),
                    colour: item.color,
                  }))}
              />
            );
          }}
        />
        {run.tranche_names.map((name, index) => (
          <Area
            key={name}
            type="monotone"
            dataKey={name}
            stackId="debt"
            stroke={TRANCHE_COLOURS[index % TRANCHE_COLOURS.length]}
            fill={TRANCHE_COLOURS[index % TRANCHE_COLOURS.length]}
            fillOpacity={0.42}
            strokeWidth={1.5}
            animationDuration={480}
          />
        ))}
        <Area
          type="monotone"
          dataKey="revolver"
          stackId="debt"
          stroke={REVOLVER_COLOUR}
          fill={REVOLVER_COLOUR}
          fillOpacity={0.42}
          strokeWidth={1.5}
          animationDuration={480}
        />
        <Area
          type="monotone"
          dataKey="cash"
          stroke={CASH_COLOUR}
          fill={CASH_COLOUR}
          fillOpacity={0.2}
          strokeWidth={1.5}
          strokeDasharray="4 3"
          animationDuration={480}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/* ---------------------------------------------------------------- exit timing */

/** MOIC compounds with every year of deleveraging; IRR is annualised, so it
 *  decays. Where the two lines cross is the argument about when to sell. */
export function ExitTimingChart({ years }: { years: ExitProfileYear[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={years} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="exit_year" {...AXIS} tickFormatter={(v) => `Y${v}`} />
        <YAxis yAxisId="moic" {...AXIS} tickFormatter={(v) => fmtMult(v)} width={54} />
        <YAxis
          yAxisId="irr"
          orientation="right"
          {...AXIS}
          tickFormatter={(v) => fmtPct(v, 0)}
          width={54}
        />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.03)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as ExitProfileYear;
            return (
              <Tip
                title={`Exit at end of year ${label}`}
                rows={[
                  { label: "MOIC", value: fmtMult(row.moic, 2) },
                  { label: "IRR", value: fmtPct(row.irr) },
                ]}
              />
            );
          }}
        />
        <Bar
          yAxisId="moic"
          dataKey="moic"
          fill={C.pineDeep}
          fillOpacity={0.55}
          radius={[2, 2, 0, 0]}
          animationDuration={480}
        />
        <Line
          yAxisId="irr"
          type="monotone"
          dataKey="irr"
          stroke={C.brass}
          strokeWidth={2}
          dot={{ r: 3, fill: C.brass, strokeWidth: 0 }}
          animationDuration={480}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------------- tornado */

/** Horizontal diverging bars around the base case, widest span at the top —
 *  a ranking of what actually moves the answer. */
export function TornadoChart({
  drivers,
  baseIrr,
}: {
  drivers: TornadoDriver[];
  baseIrr: number | null;
}) {
  const base = baseIrr ?? 0;
  const data = drivers
    .slice()
    .reverse()
    .map((d) => ({
      driver: d.driver,
      low: (d.low_irr ?? base) - base,
      high: (d.high_irr ?? base) - base,
      lowIrr: d.low_irr,
      highIrr: d.high_irr,
    }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(240, data.length * 42)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 8, right: 16, left: 8, bottom: 4 }}
        barCategoryGap="26%"
      >
        <CartesianGrid horizontal={false} />
        <XAxis
          type="number"
          {...AXIS}
          tickFormatter={(v) => fmtPct(base + v, 0)}
        />
        <YAxis type="category" dataKey="driver" {...AXIS} width={210} />
        <ReferenceLine x={0} stroke={C.text3} strokeWidth={1} />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.03)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as (typeof data)[number];
            return (
              <Tip
                title={row.driver}
                rows={[
                  { label: "Downside", value: fmtPct(row.lowIrr), colour: C.rust },
                  { label: "Base", value: fmtPct(baseIrr), colour: C.text2 },
                  { label: "Upside", value: fmtPct(row.highIrr), colour: C.pine },
                ]}
              />
            );
          }}
        />
        <Bar dataKey="low" fill={C.rust} fillOpacity={0.78} animationDuration={420} />
        <Bar dataKey="high" fill={C.pine} fillOpacity={0.78} animationDuration={420} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ---------------------------------------------------------------- credit view */

/** Net leverage against the covenant convention it would be tested against. */
export function LeverageChart({ credit }: { credit: CreditYear[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={credit} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <defs>
          <linearGradient id="levFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.pine} stopOpacity={0.34} />
            <stop offset="100%" stopColor={C.pine} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="year" {...AXIS} tickFormatter={(v) => `Y${v}`} />
        <YAxis {...AXIS} tickFormatter={(v) => fmtMult(v)} width={54} domain={[0, "auto"]} />
        <ReferenceLine
          y={6}
          stroke={C.rust}
          label={{
            value: "6.0× covenant convention",
            position: "insideTopRight",
            fill: C.rust,
            fontSize: 10,
            fontFamily: "IBM Plex Mono",
          }}
        />
        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as CreditYear;
            return (
              <Tip
                title={`Year ${label}`}
                rows={[{ label: "Net debt / EBITDA", value: fmtMult(row.net_leverage, 2) }]}
              />
            );
          }}
        />
        <Area
          type="monotone"
          dataKey="net_leverage"
          stroke={C.pine}
          strokeWidth={2}
          fill="url(#levFill)"
          animationDuration={480}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Both coverage tests, against the 2.0× floor a credit agreement would set. */
export function CoverageChart({ credit }: { credit: CreditYear[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={credit} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="year" {...AXIS} tickFormatter={(v) => `Y${v}`} />
        <YAxis {...AXIS} tickFormatter={(v) => fmtMult(v)} width={54} domain={[0, "auto"]} />
        <ReferenceLine
          y={2}
          stroke={C.rust}
          label={{
            value: "2.0× floor",
            position: "insideTopRight",
            fill: C.rust,
            fontSize: 10,
            fontFamily: "IBM Plex Mono",
          }}
        />
        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as CreditYear;
            return (
              <Tip
                title={`Year ${label}`}
                rows={[
                  { label: "EBITDA / interest", value: fmtMult(row.interest_coverage, 2), colour: C.pine },
                  {
                    label: "(EBITDA − capex) / interest",
                    value: fmtMult(row.ebitda_less_capex_coverage, 2),
                    colour: C.brass,
                  },
                  { label: "FCF conversion", value: fmtPct(row.fcf_conversion, 0), colour: C.text2 },
                ]}
              />
            );
          }}
        />
        <Line
          type="monotone"
          dataKey="interest_coverage"
          stroke={C.pine}
          strokeWidth={2}
          dot={{ r: 3, fill: C.pine, strokeWidth: 0 }}
          animationDuration={480}
        />
        <Line
          type="monotone"
          dataKey="ebitda_less_capex_coverage"
          stroke={C.brass}
          strokeWidth={2}
          strokeDasharray="5 3"
          dot={{ r: 3, fill: C.brass, strokeWidth: 0 }}
          animationDuration={480}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------- EBITDA build */

/** Revenue and margin together: the operating case that everything else rests
 *  on, shown so a reviewer can sanity-check it before reading any return. */
export function OperatingChart({ run }: { run: RunResult }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={run.years} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="year" {...AXIS} tickFormatter={(v) => `Y${v}`} />
        <YAxis yAxisId="abs" {...AXIS} tickFormatter={(v) => fmtMoney(v)} width={68} />
        <YAxis
          yAxisId="pct"
          orientation="right"
          {...AXIS}
          tickFormatter={(v) => fmtPct(v, 0)}
          width={54}
          domain={["auto", "auto"]}
        />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.03)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as RunResult["years"][number];
            return (
              <Tip
                title={`Year ${label}`}
                rows={[
                  { label: "Revenue", value: fmtMoney(row.revenue) },
                  { label: "EBITDA", value: fmtMoney(row.ebitda) },
                  { label: "Margin", value: fmtPct(row.ebitda_margin) },
                  { label: "Capex", value: fmtMoney(row.capex) },
                ]}
              />
            );
          }}
        />
        <Bar
          yAxisId="abs"
          dataKey="revenue"
          fill={C.edge}
          radius={[2, 2, 0, 0]}
          animationDuration={480}
        />
        <Bar
          yAxisId="abs"
          dataKey="ebitda"
          fill={C.pineDeep}
          radius={[2, 2, 0, 0]}
          animationDuration={480}
        />
        <Line
          yAxisId="pct"
          type="monotone"
          dataKey="ebitda_margin"
          stroke={C.brass}
          strokeWidth={2}
          dot={{ r: 3, fill: C.brass, strokeWidth: 0 }}
          animationDuration={480}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export { NA };

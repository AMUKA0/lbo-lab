/**
 * Tables.
 *
 * The annual schedule is laid out the way a model is laid out in Excel — line
 * items down, years across — rather than one row per year. That is not
 * decoration: it is the orientation anyone reviewing this will read it in, and
 * it lets a whole section (operating build, interest and tax, the waterfall)
 * be scanned across time in a single glance.
 *
 * Nothing is summarised away. Every field the engine computes appears here,
 * including the ones a lighter tool would hide: the NOL roll-forward, the
 * undrawn commitment fee, and the number of passes the interest solve needed.
 */

import type { CreditYear, RunResult, Scenario, YearRow } from "../api/types";
import { fmtMoney, fmtMult, fmtPct, fmtSigned, NA } from "../lib/format";

/* ------------------------------------------------------------ sources & uses */

export function SourcesUsesTable({
  run,
  entryEbitda,
}: {
  run: RunResult;
  entryEbitda: number;
}) {
  const su = run.sources_uses;
  const uses: [string, number][] = [
    ["Purchase of enterprise", su.entry_ev],
    ["Transaction fees", su.transaction_fees],
    ["Financing fees", su.financing_fees],
    ["Cash to balance sheet", su.cash_to_balance_sheet],
  ];
  const sources: [string, number][] = [
    ...Object.entries(su.tranche_amounts),
    ["Sponsor equity", su.sponsor_equity],
  ];

  return (
    <div className="grid-2">
      <div>
        <table className="data">
          <thead>
            <tr>
              <th>Uses</th>
              <th>Amount</th>
              <th>% of total</th>
            </tr>
          </thead>
          <tbody>
            {uses.map(([label, value]) => (
              <tr key={label}>
                <td className="row-label">{label}</td>
                <td>{fmtMoney(value)}</td>
                <td className="mute">{fmtPct(value / su.total_uses)}</td>
              </tr>
            ))}
            <tr className="total">
              <td className="row-label">Total uses</td>
              <td>{fmtMoney(su.total_uses)}</td>
              <td className="mute">100.0%</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div>
        <table className="data">
          <thead>
            <tr>
              <th>Sources</th>
              <th>Amount</th>
              <th>× EBITDA</th>
            </tr>
          </thead>
          <tbody>
            {sources.map(([label, value]) => (
              <tr key={label}>
                <td className="row-label">{label}</td>
                <td>{fmtMoney(value)}</td>
                <td className="mute">{fmtMult(value / entryEbitda, 2)}</td>
              </tr>
            ))}
            <tr className="total">
              <td className="row-label">Total sources</td>
              <td>{fmtMoney(su.total_sources)}</td>
              <td className="mute">{fmtMult(su.total_sources / entryEbitda, 2)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ schedule */

type Row = {
  label: string;
  get: (y: YearRow) => number;
  format?: (v: number) => string;
  emphasis?: boolean;
  indent?: boolean;
};

function Section({
  title,
  rows,
  years,
}: {
  title: string;
  rows: Row[];
  years: YearRow[];
}) {
  return (
    <>
      <tr>
        <td
          className="row-label"
          colSpan={years.length + 1}
          style={{
            paddingTop: 16,
            fontFamily: "var(--mono)",
            fontSize: "0.64rem",
            letterSpacing: "0.13em",
            textTransform: "uppercase",
            color: "var(--pine-deep)",
          }}
        >
          {title}
        </td>
      </tr>
      {rows.map((row) => (
        <tr key={row.label}>
          <td
            className="row-label"
            style={{
              paddingLeft: row.indent ? 22 : undefined,
              color: row.emphasis ? "var(--text)" : undefined,
              fontWeight: row.emphasis ? 600 : undefined,
            }}
          >
            {row.label}
          </td>
          {years.map((y) => (
            <td key={y.year} style={row.emphasis ? { fontWeight: 600 } : undefined}>
              {(row.format ?? ((v: number) => fmtMoney(v, 1)))(row.get(y))}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function ScheduleTable({ run }: { run: RunResult }) {
  const years = run.years;

  const operating: Row[] = [
    { label: "Revenue", get: (y) => y.revenue },
    { label: "EBITDA", get: (y) => y.ebitda, emphasis: true },
    { label: "EBITDA margin", get: (y) => y.ebitda_margin, format: (v) => fmtPct(v) },
    { label: "Less: D&A", get: (y) => -y.da },
    { label: "EBIT", get: (y) => y.ebit, emphasis: true },
  ];

  const financing: Row[] = [
    { label: "Cash interest", get: (y) => -y.cash_interest_total },
    { label: "PIK accrual", get: (y) => -y.pik_accrual_total },
    { label: "Financing-fee amortisation", get: (y) => -y.fee_amortisation },
    { label: "Undrawn commitment fee", get: (y) => -y.revolver_undrawn_fee },
    { label: "Pre-tax income", get: (y) => y.ebt, emphasis: true },
  ];

  const tax: Row[] = [
    { label: "NOL opening", get: (y) => y.nol_opening, indent: true },
    { label: "NOL used", get: (y) => -y.nol_used, indent: true },
    { label: "NOL closing", get: (y) => y.nol_closing, indent: true },
    { label: "Taxes", get: (y) => -y.taxes },
    { label: "Net income", get: (y) => y.net_income, emphasis: true },
  ];

  const cashflow: Row[] = [
    { label: "Add back: D&A", get: (y) => y.da, indent: true },
    { label: "Add back: fee amortisation", get: (y) => y.fee_amortisation, indent: true },
    { label: "Add back: PIK", get: (y) => y.pik_accrual_total, indent: true },
    { label: "Less: capex", get: (y) => -y.capex, indent: true },
    { label: "Less: ΔNWC", get: (y) => -y.delta_nwc, indent: true },
    {
      label: "Cash available for debt service",
      get: (y) => y.cash_available_for_debt_service,
      emphasis: true,
    },
  ];

  const waterfall: Row[] = [
    ...run.tranche_names.flatMap((name): Row[] => [
      {
        label: `${name} — mandatory`,
        get: (y) => -(y.tranches.find((t) => t.name === name)?.mandatory_repayment ?? 0),
        indent: true,
      },
      {
        label: `${name} — sweep`,
        get: (y) => -(y.tranches.find((t) => t.name === name)?.sweep_repayment ?? 0),
        indent: true,
      },
    ]),
    // Only when a toggle was actually elected somewhere in the hold.
    ...(run.years.some((y) => y.pik_elections.length)
      ? ([
          {
            label: "PIK toggle elected",
            get: (y) => (y.pik_elections.length ? 1 : 0),
            format: (v) => (v ? "yes" : "—"),
            indent: true,
          },
        ] as Row[])
      : []),
    { label: "Revolver draw", get: (y) => y.revolver_draw, indent: true },
    { label: "Revolver repayment", get: (y) => -y.revolver_repayment, indent: true },
    // Only shown when the deal actually has one, so an ordinary deal's schedule
    // doesn't carry three permanently empty rows.
    ...(run.years.some((y) => y.recap_raised !== 0)
      ? ([
          { label: "Recap debt raised", get: (y) => y.recap_raised, indent: true },
          { label: "Recap financing fee", get: (y) => -y.recap_fee, indent: true },
          { label: "Dividend to sponsor", get: (y) => y.recap_dividend, emphasis: true },
        ] as Row[])
      : []),
  ];

  const balances: Row[] = [
    ...run.tranche_names.map(
      (name): Row => ({
        label: `${name} closing`,
        get: (y) => y.tranches.find((t) => t.name === name)?.closing ?? 0,
        indent: true,
      }),
    ),
    { label: "Revolver closing", get: (y) => y.revolver_closing, indent: true },
    { label: "Total debt", get: (y) => y.total_debt_closing, emphasis: true },
    { label: "Cash", get: (y) => y.closing_cash },
    { label: "Net debt", get: (y) => y.net_debt_closing, emphasis: true },
    {
      label: "Interest solve passes",
      get: (y) => y.interest_iterations,
      format: (v) => v.toFixed(0),
    },
  ];

  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Line item</th>
            {years.map((y) => (
              <th key={y.year}>Year {y.year}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <Section title="Operating build" rows={operating} years={years} />
          <Section title="Financing charges" rows={financing} years={years} />
          <Section title="Tax, with NOL carryforward" rows={tax} years={years} />
          <Section title="Cash flow" rows={cashflow} years={years} />
          <Section title="Debt waterfall" rows={waterfall} years={years} />
          <Section title="Closing balances" rows={balances} years={years} />
        </tbody>
      </table>
    </div>
  );
}

/* -------------------------------------------------------------- credit table */

export function CreditTable({ credit }: { credit: CreditYear[] }) {
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Metric</th>
            {credit.map((c) => (
              <th key={c.year}>Year {c.year}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="row-label">Net debt / EBITDA</td>
            {credit.map((c) => (
              <td key={c.year} className={c.net_leverage == null ? "na" : undefined}>
                {fmtMult(c.net_leverage, 2)}
              </td>
            ))}
          </tr>
          <tr>
            <td className="row-label">EBITDA / cash interest</td>
            {credit.map((c) => (
              <td
                key={c.year}
                className={c.interest_coverage == null ? "na" : undefined}
                style={
                  c.interest_coverage != null && c.interest_coverage < 2
                    ? { color: "var(--rust)" }
                    : undefined
                }
              >
                {fmtMult(c.interest_coverage, 2)}
              </td>
            ))}
          </tr>
          {/* Both measures, because on a PIK-heavy structure the cash figure
              alone flatters the deal badly — it stays comfortable long after the
              balance has started compounding away from the business. */}
          <tr>
            <td className="row-label">EBITDA / total interest (incl. PIK)</td>
            {credit.map((c) => (
              <td
                key={c.year}
                className={c.total_interest_coverage == null ? "na" : undefined}
                style={
                  c.total_interest_coverage != null && c.total_interest_coverage < 2
                    ? { color: "var(--rust)" }
                    : undefined
                }
              >
                {fmtMult(c.total_interest_coverage, 2)}
              </td>
            ))}
          </tr>
          <tr>
            <td className="row-label">(EBITDA − capex) / interest</td>
            {credit.map((c) => (
              <td
                key={c.year}
                className={c.ebitda_less_capex_coverage == null ? "na" : undefined}
                style={
                  c.ebitda_less_capex_coverage != null && c.ebitda_less_capex_coverage < 2
                    ? { color: "var(--rust)" }
                    : undefined
                }
              >
                {fmtMult(c.ebitda_less_capex_coverage, 2)}
              </td>
            ))}
          </tr>
          <tr>
            <td className="row-label">FCF conversion</td>
            {credit.map((c) => (
              <td key={c.year} className={c.fcf_conversion == null ? "na" : undefined}>
                {fmtPct(c.fcf_conversion, 0)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------ scenario table */

export function ScenarioTable({ scenarios }: { scenarios: Scenario[] }) {
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Case</th>
            <th>IRR</th>
            <th>MOIC</th>
            <th>Exit equity</th>
            <th>Exit multiple</th>
            <th>Exit leverage</th>
            <th>Min. coverage</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s) => (
            <tr key={s.name}>
              <td className="row-label">
                {s.name}
                {s.failed && (
                  <span className="neg" style={{ marginLeft: 8, fontSize: "0.74rem" }}>
                    structure fails
                  </span>
                )}
                {!s.failed && s.wiped_out && (
                  <span className="neg" style={{ marginLeft: 8, fontSize: "0.74rem" }}>
                    equity wiped out
                  </span>
                )}
              </td>
              <td className={s.irr == null ? "na" : s.irr >= 0.2 ? "pos" : undefined}>
                {fmtPct(s.irr)}
              </td>
              <td className={s.moic == null ? "na" : undefined}>{fmtMult(s.moic, 2)}</td>
              <td className={s.exit_equity == null ? "na" : undefined}>
                {s.exit_equity == null ? NA : fmtMoney(s.exit_equity)}
              </td>
              <td className="mute">{fmtMult(s.exit_multiple)}</td>
              <td className={s.exit_net_leverage == null ? "na" : undefined}>
                {fmtMult(s.exit_net_leverage, 2)}
              </td>
              <td
                className={s.min_interest_coverage == null ? "na" : undefined}
                style={
                  s.min_interest_coverage != null && s.min_interest_coverage < 2
                    ? { color: "var(--rust)" }
                    : undefined
                }
              >
                {fmtMult(s.min_interest_coverage, 2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* --------------------------------------------------------------- bridge table */

/** The bridge as numbers, with the reconciliation shown rather than claimed. */
export function BridgeTable({ run }: { run: RunResult }) {
  const b = run.bridge;
  // A run that never reached an exit has no gain to decompose.
  if (!b) return null;
  const rows: [string, number][] = [
    ["EBITDA growth × entry multiple", b.ebitda_growth],
    ["Multiple change × exit EBITDA", b.multiple_expansion],
    ["Net debt paydown (from operations)", b.deleveraging],
    ...(b.divestitures !== 0
      ? ([["Divestiture proceeds to debt", b.divestitures]] as [string, number][])
      : []),
    ...(b.recapitalisation !== 0
      ? ([["Recap debt raised (gross)", b.recapitalisation]] as [string, number][])
      : []),
    // Every non-zero component must appear. Omitting one and then printing a
    // reconciliation underneath is worse than printing no reconciliation at all:
    // this row was missing, so Hilton's realised bridge displayed rows summing to
    // $15,398m under a stated gain of $14,598m, with "0.00 — exact" beneath it.
    ...(b.follow_on_equity !== 0
      ? ([["Follow-on sponsor capital", b.follow_on_equity]] as [string, number][])
      : []),
    ["Fees (entry, financing, recap, exit)", b.fee_drag],
  ];
  return (
    <table className="data" style={{ marginTop: 8 }}>
      <thead>
        <tr>
          <th>Driver</th>
          <th>Contribution</th>
          <th>% of gain</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <td className="row-label">{label}</td>
            <td className={value >= 0 ? "pos" : "neg"}>{fmtSigned(value)}</td>
            {/* Suppressed on a loss. Dividing by a negative gain inverts every
                sign — RJR showed EBITDA growth at −347% and fees at +204% — which
                is worse than showing nothing. */}
            <td className="mute">
              {b.equity_gain > 0 ? fmtPct(value / b.equity_gain, 0) : NA}
            </td>
          </tr>
        ))}
        {b.dividends !== 0 && (
          <tr>
            <td className="row-label mute" style={{ fontSize: "0.8rem" }}>
              of which returned early as recap dividends
            </td>
            <td className="mute">{fmtSigned(b.dividends)}</td>
            <td />
          </tr>
        )}
        <tr className="total">
          <td className="row-label">
            {b.dividends !== 0 || b.follow_on_equity !== 0
              ? "Total value created"
              : "Equity gain"}
          </td>
          <td>{fmtSigned(b.equity_gain)}</td>
          <td className="mute">100%</td>
        </tr>
        <tr>
          <td className="row-label mute" style={{ fontSize: "0.8rem" }}>
            Reconciliation error
          </td>
          <td className="mute" style={{ fontSize: "0.8rem" }}>
            {Math.abs(b.reconciliation_error) < 1e-6
              ? "0.00 — exact"
              : b.reconciliation_error.toExponential(2)}
          </td>
          <td />
        </tr>
      </tbody>
    </table>
  );
}

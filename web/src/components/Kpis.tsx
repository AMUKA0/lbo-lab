/**
 * The headline strip and the calibration flags.
 *
 * The strip is the only place in the app that is allowed to be big, because it
 * answers the first two questions anyone asks — what's the return, and what did
 * it cost. Everything under it is the evidence.
 */

import type { Flag, RunResult } from "../api/types";
import { fmtMoney, fmtMult, fmtPct } from "../lib/format";

export function KpiStrip({ run }: { run: RunResult }) {
  const entryLev = run.entry_net_leverage;
  const exitLev = run.exit_net_leverage;
  const deleveraged = entryLev != null && exitLev != null ? entryLev - exitLev : null;
  const dividends = run.bridge?.dividends ?? 0;

  return (
    <div className="kpi-strip">
      <Kpi
        k="Sponsor IRR"
        v={fmtPct(run.irr)}
        accent
        sub={run.wiped_out ? "equity wiped out" : `over ${run.years.length} years`}
      />
      <Kpi
        k="MOIC"
        v={fmtMult(run.moic, 2)}
        sub={
          dividends
            ? `on ${fmtMoney(run.entry_equity)} in, ${fmtMoney(run.bridge?.total_proceeds)} back`
            : `${fmtMoney(run.entry_equity)} → ${fmtMoney(run.exit_equity)}`
        }
      />
      {/* Only when there is one. IRR and MOIC alone cannot show that capital
          came back early, which is the entire reason a sponsor recaps. */}
      {dividends > 0 && (
        <Kpi
          k="Recap dividends"
          v={fmtMoney(dividends)}
          sub={`${fmtPct(dividends / run.entry_equity, 0)} of the cheque, returned early`}
        />
      )}
      <Kpi k="Equity cheque" v={fmtMoney(run.entry_equity)} sub="at close" />
      <Kpi
        k="Entry leverage"
        v={fmtMult(entryLev, 2)}
        sub={`${fmtMoney(run.sources_uses.total_debt)} of debt`}
      />
      <Kpi
        k="Exit leverage"
        v={fmtMult(exitLev, 2)}
        sub={deleveraged != null ? `${fmtMult(deleveraged, 2)} of deleveraging` : undefined}
      />
      <Kpi
        k="Exit equity"
        v={fmtMoney(run.exit_equity)}
        sub={`after ${fmtMoney(run.exit_fees)} of sale costs`}
      />
    </div>
  );
}

function Kpi({
  k,
  v,
  sub,
  accent,
}: {
  k: string;
  v: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="kpi">
      <span className="k">{k}</span>
      <span className={`v${accent ? " accent" : ""}`}>{v}</span>
      {sub && <span className="sub">{sub}</span>}
    </div>
  );
}

/**
 * Guardrails. A flag never blocks a run — you are allowed to model 2007, the
 * lab just tells you that you are — so these are advisory in tone and always
 * carry the source of the band they are citing.
 */
export function Flags({ flags }: { flags: Flag[] }) {
  if (flags.length === 0) {
    return (
      <div className="flags">
        <div className="flag info">
          <span className="flag-icon" aria-hidden="true">
            ✓
          </span>
          <span className="flag-body">
            Every assumption sits inside its published market band.
            <span className="flag-src">
              Bands compiled from Bain, PitchBook LCD and S&amp;P survey data
            </span>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flags">
      {flags.map((flag) => (
        <div className={`flag ${flag.level}`} key={`${flag.field}-${flag.message}`}>
          <span className="flag-icon" aria-hidden="true">
            {flag.level === "amber" ? "▲" : "•"}
          </span>
          <span className="flag-body">
            {flag.message}
            <span className="flag-src">{flag.source}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * One case study.
 *
 * The page is ordered as an argument, not as a dashboard. The thesis and the
 * sourced inputs come first, so that by the time you reach a number you already
 * know where it came from and how much weight it will bear. The comparison strip
 * comes next. The outcome comes *after* the model's verdict, deliberately — the
 * interesting question is what the numbers said before anyone knew the answer,
 * and putting the answer at the top would destroy that.
 *
 * The last section is the one that matters most for credibility: where this
 * engine structurally cannot follow the deal. Every case in the library has at
 * least one, and none of them is closed by tuning an assumption.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchCase, type CaseColumn, type CaseDetail, type Figure } from "../api/cases";
import { BridgeWaterfall, DebtPaydownChart, OperatingChart } from "../components/charts";
import { Flags, KpiStrip } from "../components/Kpis";
import { LifecycleTimeline } from "../components/Lifecycle";
import { Card, SectionHead, Skeleton, Tabs } from "../components/primitives";
import { BridgeTable, CreditTable, ScheduleTable, SourcesUsesTable } from "../components/tables";
import { fmtMult, fmtPct, NA } from "../lib/format";

type ColumnId = "underwriting" | "realised";

const BASIS_NOTE: Record<Figure["basis"], string> = {
  reported: "Appears in a filing, press release or contemporaneous report.",
  derived: "Follows arithmetically from reported figures.",
  estimated: "A judgement call. The reasoning is given alongside.",
};

function bn(millions: number | null | undefined): string {
  if (millions === null || millions === undefined) return NA;
  return `$${(millions / 1000).toFixed(1)}bn`;
}

/** Which wall was hit. Three different findings with three different remedies:
 *  collapsing them into "failed" throws away the more interesting half. */
const BREAK_HEADLINE: Record<string, string> = {
  liquidity: "Liquidity break",
  covenant: "Covenant breach",
  maturity: "Maturity wall",
};

const BREAK_BODY: Record<string, string> = {
  liquidity:
    "Operating cash flow no longer covers contractual interest and amortisation, and the revolver cannot fund the gap. The engine stops rather than printing a schedule that quietly runs a negative cash balance — which is what a model without a liquidity constraint would do, and why such models never show a deal failing.",
  covenant:
    "Solvency is not the question here: the company is paying every coupon on time. A maintenance covenant is tested on a ratio, and breaching it is an event of default that hands the lenders the keys unless it is waived, amended or cured. In practice it is almost always one of those three, at a price — and this is the mode most 2008–09 sponsor distress actually took.",
  maturity:
    "The business was servicing its interest. What it could not do was repay or roll a wall of principal falling due inside the hold. That is a failure in the capital markets rather than in the operating business, and it is how the largest buyout ever done actually ended.",
};

export function CaseStudy() {
  const { slug = "" } = useParams();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [column, setColumn] = useState<ColumnId>("underwriting");

  useEffect(() => {
    setData(null);
    setError(null);
    setColumn("underwriting");
    const controller = new AbortController();
    fetchCase(slug, controller.signal)
      .then(setData)
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Could not load the case.");
      });
    return () => controller.abort();
  }, [slug]);

  if (error) {
    return (
      <main className="landing">
        <div className="notice notice-bad">{error}</div>
        <Link className="btn" to="/cases">
          ← Back to the library
        </Link>
      </main>
    );
  }
  if (!data) {
    return (
      <main className="landing">
        <Skeleton height={520} />
      </main>
    );
  }

  const active: CaseColumn | null = column === "underwriting" ? data.underwriting : data.realised;

  return (
    <>
      <main className="landing case-page">
        <Link className="back-link" to="/cases">
          ← Case studies
        </Link>

        <header className="case-head">
          <div className="eyebrow">
            {data.sector} · signed {data.signed} · closed {data.closed}
          </div>
          <h1>{data.name}</h1>
          <div className="case-sponsor">{data.sponsor}</div>
          <div className="case-headline-stats">
            <HeadStat k="Enterprise value" v={bn(data.entry_ev)} />
            {/* In millions, not billions: this is the denominator of the entry
                multiple, and "$1.7bn" would make that division uncheckable. */}
            <HeadStat
              k="Entry EBITDA"
              v={`$${Math.round(data.entry_ebitda).toLocaleString("en-US")}m`}
            />
            <HeadStat k="Entry multiple" v={fmtMult(data.entry_multiple)} />
            <HeadStat k="Leverage at close" v={`${data.leverage_turns.toFixed(1)}×`} />
          </div>
        </header>

        <Card
          title="The underwriting case"
          note="Reconstructed from what was knowable before close. No outcome figure is used as an input."
        >
          <p className="prose">{data.thesis}</p>
        </Card>

        <SectionHead
          title="The inputs, and where each one comes from"
          eyebrow="Provenance"
        />
        <div className="provenance">
          {data.provenance.map((f) => (
            <div className="prov-row" key={f.label}>
              <div className="prov-label">
                <div className="pl-name">{f.label}</div>
                <div className="pl-value">{f.value}</div>
              </div>
              <div className="prov-body">
                <span className={`basis basis-${f.basis}`} title={BASIS_NOTE[f.basis]}>
                  {f.basis}
                </span>
                <p>{f.note}</p>
                {f.source && (
                  <a className="prov-src" href={f.source.url} target="_blank" rel="noreferrer">
                    {f.source.label} →
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>

        <SectionHead
          title="Model versus reality"
          eyebrow="Three columns, three different questions"
        />
        <div className="verdict-strip">
          <VerdictCard
            title="Modelled — as signed"
            sub="Pre-close information only. No hindsight."
            irr={data.underwriting.irr}
            moic={data.underwriting.moic}
            years={data.underwriting.assumptions.hold_years}
            failed={data.underwriting.failed}
            breaksInYear={data.underwriting.breaks_in_year}
            survivedYears={data.underwriting.survived_years}
          />
          <VerdictCard
            title="Modelled — actual path"
            sub="Same structure, fed the operating path that happened."
            irr={data.realised?.irr ?? null}
            moic={data.realised?.moic ?? null}
            years={data.realised?.assumptions.hold_years}
            failed={data.realised?.failed ?? false}
            breaksInYear={data.realised?.breaks_in_year}
            survivedYears={data.realised?.survived_years}
          />
          <VerdictCard
            title="What actually happened"
            sub={data.outcome.exit_route}
            irr={data.outcome.realised_irr}
            moic={data.outcome.realised_moic}
            years={data.outcome.holding_years}
            failed={false}
            actual
            confidence={data.outcome.confidence}
          />
        </div>

        <Card title={data.outcome.headline} eyebrow={`Exited ${data.outcome.exit_year}`}>
          <p className="prose">{data.outcome.narrative}</p>
        </Card>

        <SectionHead
          title="The model, run in full"
          eyebrow="Same engine as the simulator — nothing special-cased"
        />
        <Tabs
          tabs={[
            { id: "underwriting", label: "As signed" },
            { id: "realised", label: "Actual operating path" },
          ]}
          active={column}
          onChange={(id) => setColumn(id as ColumnId)}
        />

        {active && (
          <div className="column-actions">
            <a
              className="btn"
              href={`/api/cases/${slug}/${column}.xlsx`}
              download
            >
              Download this column as a live Excel model
            </a>
            <span className="field-note">
              {active.failed
                ? "Formulas, not values — and the schedule stops at the break, as it does here. The workbook says so on its Inputs sheet, and its Returns sheet deliberately prints no IRR: there was no exit, so a return struck on that balance sheet would be an answer to a question nobody asked."
                : "Formulas, not values. Every calculated cell carries one, inputs are blue named ranges, and iterative calculation is switched on in the file because the interest circularity is real in Excel too."}
            </span>
          </div>
        )}

        {active?.note && <div className="column-note">{active.note}</div>}

        {!active && (
          <div className="notice">No realised path is modelled for this case.</div>
        )}

        {active?.failed && (
          <div className="notice notice-bad">
            <strong>
              {BREAK_HEADLINE[active.failure_kind ?? "liquidity"]} in year{" "}
              {active.breaks_in_year}, after {active.survived_years}{" "}
              {active.survived_years === 1 ? "year" : "years"} of debt service.
            </strong>
            <div style={{ marginTop: "var(--s2)" }}>
              {BREAK_BODY[active.failure_kind ?? "liquidity"]} The years it{" "}
              <em>did</em> service are below, so the path into the break is legible
              rather than merely asserted.
            </div>
          </div>
        )}

        {/* The account of the break year. Three claims kept visually apart,
            because collapsing them is how a model's limits disappear into a
            narrative: what happened, what the model computed, and what the
            model could not see — the last being why the two differ. */}
        {active?.break_note && (
          <div className="break-note">
            <div className="bn-head">
              <span className="bn-year">{active.break_note.calendar}</span>
              <h4>{active.break_note.headline}</h4>
            </div>
            <div className="bn-grid">
              <BreakPanel
                label="What happened"
                tone="fact"
                body={active.break_note.what_happened}
              />
              <BreakPanel
                label="What the engine saw"
                tone="model"
                body={active.break_note.what_the_engine_saw}
              />
              <BreakPanel
                label="What the engine cannot see"
                tone="limit"
                body={active.break_note.what_the_engine_cannot_see}
              />
            </div>
          </div>
        )}

        {active?.partial_run && (
          <>
            <Flags flags={active.partial_run.flags} />
            <Card
              title="Lifetime of the investment — to the break"
              note="The decisions and pressure points on the way to running out of liquidity."
            >
              <LifecycleTimeline
                events={active.partial_run.lifecycle.filter((e) => e.kind !== "exit")}
                holdYears={active.survived_years + 1}
              />
            </Card>
            <Card
              title={`Schedule to the break — years 1 to ${active.survived_years}`}
              note="No exit occurred, so this carries no IRR, MOIC or exit equity. It is the operating and debt-service record up to the point the structure stopped funding itself."
            >
              <ScheduleTable run={active.partial_run} />
            </Card>
            <Card title="Credit statistics" eyebrow="Watch coverage fall">
              <CreditTable credit={active.partial_run.credit} />
            </Card>
          </>
        )}

        {active?.run && (
          <>
            <KpiStrip run={active.run} />
            <Flags flags={active.run.flags} />

            <Card
              title="Lifetime of the investment"
              note="The hold as a sequence of moments rather than a table of years — every decision the structure forced, and what each one cost."
            >
              <LifecycleTimeline
                events={active.run.lifecycle}
                holdYears={active.assumptions.hold_years}
              />
            </Card>

            <div className="grid-2">
              <Card
                title="Value creation bridge"
                eyebrow="Reconciles exactly"
              >
                <BridgeWaterfall bridge={active.run.bridge} />
                <BridgeTable run={active.run} />
              </Card>
              <Card title="Sources & uses" eyebrow="Equity is the plug">
                <SourcesUsesTable
                  run={active.run}
                  entryEbitda={active.assumptions.entry_ebitda}
                />
              </Card>
            </div>

            <div className="grid-2">
              <Card title="Debt paydown" eyebrow="By tranche">
                <DebtPaydownChart run={active.run} />
              </Card>
              <Card title="Operating build" eyebrow="Revenue & margin">
                <OperatingChart run={active.run} />
              </Card>
            </div>

            <Card title="Credit statistics" eyebrow="The lender's view">
              <CreditTable credit={active.run.credit} />
            </Card>

            <Card
              title="Annual schedule"
              note="Line items down, years across — including the NOL roll-forward and the pass count of the interest solve."
            >
              <ScheduleTable run={active.run} />
            </Card>
          </>
        )}

        <SectionHead title="What they could not have known" eyebrow="Fair and unfair criticism" />
        <Card>
          <p className="prose">{data.could_not_have_known}</p>
        </Card>

        {data.column_deltas.length > 0 && (
          <>
            <SectionHead
              title="What differs between the two columns"
              eyebrow="Beyond the operating path itself"
            />
            <p className="prose" style={{ marginBottom: "var(--s4)" }}>
              The capital structure is identical in both — same EBITDA, same entry
              multiple, same tranches at the same rates; a test enforces it. These are
              the remaining inputs that differ. They are here because a reviewer found
              that Hilton's realised column quietly carried 150bp less capex, and that,
              not the revenue collapse, was the difference between running eleven years
              and breaking in year two.
            </p>
            <table className="data" style={{ marginBottom: "var(--s7)" }}>
              <thead>
                <tr>
                  <th>Input</th>
                  <th>As signed</th>
                  <th>Actual path</th>
                </tr>
              </thead>
              <tbody>
                {data.column_deltas.map((d) => (
                  <tr key={d.field}>
                    <td className="row-label">{d.field}</td>
                    <td>{d.underwriting}</td>
                    <td>{d.realised}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <SectionHead
          title="Where this model cannot follow the deal"
          eyebrow="Stated, not closed"
        />
        <ul className="caveat-list">
          {data.model_caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>

        {data.sources.length > 0 && (
          <>
            <SectionHead title="Sources" eyebrow="For this case" />
            <ul className="source-list">
              {data.sources.map((s) => (
                <li key={s.key}>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </main>

      <footer className="site-footer">
        <span>LBO Lab</span>
        <span className="mute">
          A reconstruction from public sources, not the sponsor's own model.
        </span>
        <Link to="/simulator" style={{ marginLeft: "auto" }}>
          Open the simulator →
        </Link>
      </footer>
    </>
  );
}

function BreakPanel({
  label,
  body,
  tone,
}: {
  label: string;
  body: string;
  tone: "fact" | "model" | "limit";
}) {
  return (
    <section className={`bn-panel bn-${tone}`}>
      <h5>{label}</h5>
      <p>{body}</p>
    </section>
  );
}

function HeadStat({ k, v }: { k: string; v: string }) {
  return (
    <div className="hs">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

function VerdictCard({
  title,
  sub,
  irr,
  moic,
  years,
  failed,
  breaksInYear,
  survivedYears = 0,
  actual = false,
  confidence,
}: {
  title: string;
  sub: string;
  irr: number | null;
  moic: number | null;
  years?: number;
  failed: boolean;
  breaksInYear?: number | null;
  survivedYears?: number;
  actual?: boolean;
  confidence?: string;
}) {
  return (
    <div className={`verdict-card${actual ? " is-actual" : ""}${failed ? " is-failed" : ""}`}>
      <div className="vc-title">{title}</div>
      {failed ? (
        <>
          <div className="vc-failed">Breaks in year {breaksInYear ?? "—"}</div>
          <div className="vc-msg">
            Serviced itself for {survivedYears} {survivedYears === 1 ? "year" : "years"},
            then ran out of liquidity. No exit, so no return is shown — a MOIC on a deal
            that never reached an exit would be an invention.
          </div>
        </>
      ) : (
        <div className="vc-nums">
          <div>
            <div className="vc-k">IRR</div>
            <div className="vc-v">{irr === null ? NA : fmtPct(irr)}</div>
          </div>
          <div>
            <div className="vc-k">MOIC</div>
            <div className="vc-v">{moic === null ? NA : fmtMult(moic, 2)}</div>
          </div>
          <div>
            <div className="vc-k">Hold</div>
            <div className="vc-v">{years === undefined ? NA : `${years}y`}</div>
          </div>
        </div>
      )}
      <div className="vc-sub">{sub}</div>
      {confidence && <div className="vc-conf">Figures {confidence}</div>}
    </div>
  );
}

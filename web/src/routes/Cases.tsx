/**
 * The case-study index.
 *
 * Ordered by entry multiple rather than by date or by outcome, because that
 * ordering makes the library's central argument visible before you click
 * anything: HCA at 7.7× and TXU at 8.5× sit next to each other and ended at
 * opposite extremes, while Hilton at 14.9× — the most expensive deal here by a
 * wide margin — made more money than any of them. Price matters enormously and
 * explains nothing on its own.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchCases, type CaseSummary, type SourceRef, type Verdict } from "../api/cases";
import { SectionHead, Skeleton } from "../components/primitives";
import { fmtMult, fmtPct } from "../lib/format";

const VERDICT_LABEL: Record<Verdict, string> = {
  "home run": "Home run",
  solid: "Solid",
  flat: "Flat",
  wipeout: "Wipeout",
};

/** Money in billions here, not the millions the rest of the app uses — these are
 *  $26bn deals and printing "26,008" would make them harder to read, not more
 *  precise. */
function bn(millions: number): string {
  return `$${(millions / 1000).toFixed(1)}bn`;
}

export function Cases() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchCases(controller.signal)
      .then((data) => {
        setCases([...data.cases].sort((a, b) => a.entry_multiple - b.entry_multiple));
        setSources(data.sources);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Could not load the library.");
      });
    return () => controller.abort();
  }, []);

  return (
    <>
      <main className="landing">
        <section className="hero stagger" style={{ paddingBottom: "var(--s5)" }}>
          <div className="eyebrow" style={{ ["--i" as string]: 0 }}>
            Case studies · Four deals, replayed
          </div>
          <h1 style={{ ["--i" as string]: 1 }}>
            What would this model have said <em>at the time?</em>
          </h1>
          <p style={{ ["--i" as string]: 2 }}>
            Each deal is reconstructed from information available before close — no
            outcome figure is allowed anywhere near an input — and run through the same
            engine as the simulator. Then it is run a second time on the operating path
            that actually happened, which is the model marking its own homework. Every
            assumption carries its source and says whether it is reported, derived, or a
            judgement call.
          </p>
        </section>

        {error && <div className="notice notice-bad">{error}</div>}
        {!cases && !error && <Skeleton height={420} />}

        {cases && (
          <>
            <div className="case-grid">
              {cases.map((c) => (
                <CaseCard key={c.slug} c={c} />
              ))}
            </div>

            <SectionHead
              title="How the library is built"
              eyebrow="The method, before the deals"
            />
            <div className="method-grid">
              <ul>
                <li>
                  <strong>No hindsight in the inputs.</strong> Growth, margin and exit-
                  multiple assumptions are set to the trailing trend, the consensus, or
                  the banker ranges in the proxy — never to what followed. Where a figure
                  is a judgement call it is marked <em>estimated</em> and the reasoning is
                  given.
                </li>
                <li>
                  <strong>Two columns, two questions.</strong> The underwriting column
                  asks what the model says about the deal as signed. The realised column
                  feeds it the operating path that actually occurred and asks whether the
                  engine reproduces reality. They are different questions and conflating
                  them is how case studies become stories.
                </li>
              </ul>
              <ul>
                <li>
                  <strong>Failure is a result.</strong> Three of the eight runs in this
                  library refuse to produce a schedule, because the structure cannot
                  service itself. That is the finding, not a bug — in Hilton's case the
                  model identifies the exact year Blackstone had to renegotiate.
                </li>
                <li>
                  <strong>Gaps are named, not closed.</strong> Where the engine cannot
                  follow a deal — RJR's divestitures, HCA's dividend recaps, TXU's gas
                  hedges — it is stated on the page rather than papered over by tuning an
                  assumption until the answer looks right.
                </li>
              </ul>
            </div>

            {sources.length > 0 && (
              <>
                <SectionHead title="Sources" eyebrow="Everything is traceable" />
                <ul className="source-list">
                  {sources.map((s) => (
                    <li key={s.key}>
                      <a href={s.url} target="_blank" rel="noreferrer">
                        {s.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </main>

      <footer className="site-footer">
        <span>LBO Lab</span>
        <span className="mute">
          Case assumptions are reconstructions, not the sponsors' own models — which are
          not public.
        </span>
      </footer>
    </>
  );
}

function CaseCard({ c }: { c: CaseSummary }) {
  const { outcome } = c;
  return (
    <Link className={`case-card verdict-${c.verdict.replace(" ", "-")}`} to={`/cases/${c.slug}`}>
      <div className="cc-head">
        <div>
          <h4>{c.name}</h4>
          <div className="cc-sponsor">{c.sponsor}</div>
        </div>
        <span className={`cc-verdict v-${c.verdict.replace(" ", "-")}`}>
          {VERDICT_LABEL[c.verdict]}
        </span>
      </div>

      <div className="cc-stats">
        <Stat k="Enterprise value" v={bn(c.entry_ev)} />
        <Stat k="Entry multiple" v={fmtMult(c.entry_multiple)} />
        <Stat k="Leverage" v={`${c.leverage_turns.toFixed(1)}×`} />
        <Stat
          k={`Realised (${outcome.holding_years.toFixed(0)}y)`}
          v={
            outcome.realised_moic === null
              ? "—"
              : `${fmtMult(outcome.realised_moic, 2)} · ${fmtPct(outcome.realised_irr)}`
          }
        />
      </div>

      <p className="cc-why">{c.why_it_is_here}</p>
      <div className="cc-foot">
        <span className="mute">
          {c.closed} → {outcome.exit_year}
        </span>
        <span className="cc-go">Open the case →</span>
      </div>
    </Link>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="cc-stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

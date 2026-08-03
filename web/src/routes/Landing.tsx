/**
 * The landing page.
 *
 * Written to be read by someone deciding in fifteen seconds whether the thing
 * is serious. So: what it does, what conventions it follows, and where it is
 * knowingly simplified — that last one being the part that separates a model
 * from a toy.
 */

import { Link } from "react-router-dom";

import { SectionHead } from "../components/primitives";

const FEATURES = [
  {
    no: "01",
    title: "The engine, done properly",
    body: "Sources & uses with equity as the plug, a multi-tranche schedule with mandatory amortisation and a senior-first cash sweep, PIK accretion, NOL carryforwards under a configurable §172(a) shelter, and a revolver for shortfalls — with the interest ↔ balance circularity resolved by an iterative solve, the way Excel's iterative mode does it.",
  },
  {
    no: "02",
    title: "Value-creation bridge",
    body: "Every outcome decomposed into the three drivers an investment committee actually argues about — EBITDA growth, multiple expansion, deleveraging — plus the fee drag. The bridge sums exactly to the equity gain, and the app shows you the reconciliation rather than asking you to take it on trust.",
  },
  {
    no: "03",
    title: "Calibration guardrails",
    body: "Each assumption is checked against published market bands from Bain, PitchBook LCD and S&P, and the band is drawn on the slider itself. You are allowed to model 2007; the lab just tells you that you are.",
  },
  {
    no: "04",
    title: "Tornado & scenarios",
    body: "One-at-a-time driver swings ranked by IRR impact, and a base / upside / downside / recession set run side by side — reporting whether each case's capital structure survived, not only what it returned.",
  },
  {
    no: "05",
    title: "The model in reverse",
    body: "A breakeven solver: name a target IRR and the lab bisects for the exit multiple that clears it. The distance between that and your entry multiple is how much of your return you are asking the market to hand you.",
  },
  {
    no: "06",
    title: "Four real deals, replayed",
    body: "Hilton, HCA, TXU and RJR Nabisco, each reconstructed from information available before close and run through this engine — then run again on the operating path that actually happened. Every input is sourced and labelled reported, derived or estimated. Two of the eight runs refuse to produce a schedule, which is the finding rather than a fault.",
  },
  {
    no: "07",
    title: "Excel that is actually a model",
    body: "The export is a live workbook, not a dump of the answers: every calculated cell carries a formula, inputs are blue named ranges, and iterative calculation is switched on in the file because interest on average balances is circular in Excel too. Export it, work on it in Excel, upload it back. A test writes the workbook, recalculates it with an independent evaluator and asserts it agrees with the engine line by line.",
  },
  {
    no: "08",
    title: "The lender's view",
    body: "Net leverage, interest coverage, (EBITDA − capex) coverage and FCF conversion by year, against the covenant conventions credit committees actually use. A structure that breaches them on paper doesn't get financed on those terms.",
  },
];

export function Landing() {
  return (
    <>
      <main className="landing">
        <section className="hero stagger">
          <div className="eyebrow" style={{ ["--i" as string]: 0 }}>
            LBO Lab · Deal-level buyout modelling
          </div>
          <h1 style={{ ["--i" as string]: 1 }}>
            Interrogate a leveraged buyout <em>in real time.</em>
          </h1>
          <p style={{ ["--i" as string]: 2 }}>
            A working laboratory for private-equity deal mechanics: a fully engineered LBO
            model — multi-tranche debt, cash sweep, the interest circularity solved
            properly — with the judgement layer most models skip. Market-range guardrails on
            every assumption, driver attribution, stress testing, and the model run in
            reverse.
          </p>
          <div className="hero-actions" style={{ ["--i" as string]: 3 }}>
            <Link className="btn btn-primary" to="/simulator">
              Open the simulator →
            </Link>
            <Link className="btn" to="/cases">
              Case studies
            </Link>
            <a className="btn" href="#methodology">
              Methodology ↓
            </a>
          </div>
        </section>

        <div className="stat-strip">
          <Stat v="197" k="tests · golden case solved by hand" />
          <Stat v="4" k="real deals replayed, fully sourced" />
          <Stat v="7" k="drivers in the tornado" />
          <Stat v="1e-10" k="tolerance on the interest solve" />
        </div>

        <SectionHead title="What the lab does" eyebrow="Built like the models funds run" />
        <div className="feature-grid">
          {FEATURES.map((feature) => (
            <article className="feature-card" key={feature.no}>
              <div className="fc-no">{feature.no}</div>
              <h4>{feature.title}</h4>
              <p>{feature.body}</p>
            </article>
          ))}
        </div>

        <div id="methodology">
          <SectionHead title="Methodology" eyebrow="Conventions, stated plainly" />
        </div>
        <div className="method-grid">
          <ul>
            <li>
              <strong>Entry</strong> — cash-free / debt-free; EV = EBITDA × entry multiple;
              sponsor equity is the plug.
            </li>
            <li>
              <strong>Interest</strong> — on the average of opening and closing balances, the
              advanced-model convention. The resulting circularity is resolved iteratively
              each year to a 1e-10 tolerance, and the pass count is shown in the schedule. A
              circularity-breaker toggle switches to opening-balance-only.
            </li>
            <li>
              <strong>Waterfall</strong> — mandatory amortisation (a % of <em>original</em>{" "}
              principal, the term-loan convention) → revolver repayment → cash sweep,
              senior-first, sweepable tranches only.
            </li>
            <li>
              <strong>Taxes</strong> — on EBT after all deductible interest and fee
              amortisation; losses carry forward as NOLs sheltering up to 80% of later income
              (post-TCJA §172(a)).
            </li>
          </ul>
          <ul>
            <li>
              <strong>Fees</strong> — financing fees amortise over the <em>facility tenor</em>{" "}
              per ASC 835-30, not the hold; sale-process costs come out of exit proceeds.
            </li>
            <li>
              <strong>Exit</strong> — exit multiple × terminal EBITDA, less net debt and exit
              fees; sponsor equity floored at zero for limited liability.
            </li>
            <li>
              <strong>Returns</strong> — MOIC and a bisection IRR on the sponsor's flows; the
              value bridge reconciles exactly, and credit stats cover the lender's view.
            </li>
            <li>
              <strong>Known gaps</strong> — no §163(j) interest limitation and no §382
              cap; failure is tested on liquidity only, with no covenant or maturity
              wall; no management rollover or add-ons; annual periodicity and fixed
              rates. Each is listed in the README with what it would change, because
              pretending they don't exist is how models lie.
            </li>
          </ul>
        </div>
      </main>

      <footer className="site-footer">
        <span>LBO Lab</span>
        <span className="mute">
          Engine in Python · API in FastAPI · interface in React. One tested engine behind
          both.
        </span>
        <a href="/api/docs" target="_blank" rel="noreferrer" style={{ marginLeft: "auto" }}>
          API schema →
        </a>
      </footer>
    </>
  );
}

function Stat({ v, k }: { v: string; k: string }) {
  return (
    <div className="stat-cell">
      <div className="v">{v}</div>
      <div className="k">{k}</div>
    </div>
  );
}

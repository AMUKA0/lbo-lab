/**
 * The lifetime of the investment.
 *
 * A deal is normally read as a table of years, which is the right format for
 * checking arithmetic and the wrong one for understanding what happened. This
 * is the same run told as a sequence of moments: the cheque, the decisions
 * taken under pressure, the constraints that started biting, the exit.
 *
 * Two deliberate choices:
 *
 * - **Every event explains itself.** A timeline of labels would be decoration.
 *   The value is in *why* a PIK toggle was elected in year four and what it
 *   costs, which is the sentence a reader could not have derived from the
 *   schedule without already knowing the mechanic.
 * - **Tone is carried by a rail, not by fill.** Colour-flooding the card for a
 *   "bad" event makes the page shout; a 2px left rail says the same thing and
 *   keeps the type legible.
 */

import type { LifecycleEvent } from "../api/types";

const DOT: Record<LifecycleEvent["kind"], string> = {
  entry: "●",
  pik_toggle: "◐",
  recap: "◆",
  recap_unfunded: "◇",
  revolver: "▲",
  coverage: "▲",
  leverage: "▲",
  exit: "●",
};

export function LifecycleTimeline({
  events,
  holdYears,
}: {
  events: LifecycleEvent[];
  holdYears: number;
}) {
  if (!events.length) return null;

  return (
    <ol className="lifecycle">
      {events.map((e, i) => (
        <li className={`lc-item tone-${e.tone}`} key={`${e.year}-${e.kind}-${i}`}>
          <div className="lc-marker" aria-hidden="true">
            {DOT[e.kind] ?? "●"}
          </div>
          <div className="lc-body">
            <div className="lc-head">
              <span className="lc-year">{yearLabel(e.year, holdYears)}</span>
              <span className="lc-title">{e.title}</span>
            </div>
            <p className="lc-detail">{e.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Year 0 is the close and the final year is the exit; naming them beats
 *  printing "Year 0", which reads like an off-by-one. */
function yearLabel(year: number, holdYears: number): string {
  if (year === 0) return "Close";
  if (year >= holdYears) return "Exit";
  return `Year ${year}`;
}

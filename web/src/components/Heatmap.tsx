/**
 * Entry × exit multiple IRR grid.
 *
 * Hand-built rather than pulled from a chart library, for two reasons: the
 * colour ramp is anchored to a fixed hurdle (see `irrColour`) rather than to
 * the range of the data, and empty cells must stay visibly empty. A structure
 * that fails, or a sponsor who is wiped out, produces `null` — and a null cell
 * is hatched and labelled "n/a" rather than filled with a colour that implies
 * an answer exists.
 */

import type { SensitivityResult } from "../api/types";
import { fmtMult, fmtPct, irrColour, irrTextColour } from "../lib/format";

export function Heatmap({
  data,
  entryMultiple,
  exitMultiple,
}: {
  data: SensitivityResult;
  entryMultiple: number;
  exitMultiple: number;
}) {
  const { entry_multiples: entries, exit_multiples: exits, values } = data;

  // The cell closest to the live deal gets an outline, so the grid always
  // shows you where you are standing.
  const nearest = (list: number[], target: number) =>
    list.reduce(
      (best, value, index) =>
        Math.abs(value - target) < Math.abs(list[best] - target) ? index : best,
      0,
    );
  const liveRow = nearest(entries, entryMultiple);
  const liveCol = nearest(exits, exitMultiple);

  return (
    <>
      <div
        className="heat"
        style={{ gridTemplateColumns: `72px repeat(${exits.length}, minmax(0, 1fr))` }}
      >
        <div className="heat-head" />
        {exits.map((exit) => (
          <div className="heat-head" key={`h-${exit}`}>
            {fmtMult(exit)}
          </div>
        ))}

        {entries.map((entry, i) => (
          <Row
            key={entry}
            entry={entry}
            row={values[i]}
            exits={exits}
            isLiveRow={i === liveRow}
            liveCol={liveCol}
          />
        ))}
      </div>

      <div className="heat-legend">
        <span>0%</span>
        <span
          className="bar"
          style={{
            background:
              "linear-gradient(90deg, rgba(192,101,60,0.85), rgba(192,101,60,0.15), rgba(70,181,129,0.16), rgba(70,181,129,0.84))",
          }}
        />
        <span>40%+</span>
        <span style={{ marginLeft: "auto" }}>
          Outlined cell = the deal as currently assumed · n/a = structure fails or equity wiped out
        </span>
      </div>
    </>
  );
}

function Row({
  entry,
  row,
  exits,
  isLiveRow,
  liveCol,
}: {
  entry: number;
  row: (number | null)[];
  exits: number[];
  isLiveRow: boolean;
  liveCol: number;
}) {
  return (
    <>
      <div className="heat-head" style={{ textAlign: "right", paddingRight: 10 }}>
        {fmtMult(entry)}
      </div>
      {row.map((irr, j) => {
        const live = isLiveRow && j === liveCol;
        if (irr == null) {
          return (
            <div
              className="heat-cell heat-na"
              key={`${entry}-${exits[j]}`}
              title={`Entry ${fmtMult(entry)} / exit ${fmtMult(exits[j])}: no financeable structure`}
              style={live ? { outline: `1.5px solid ${"var(--text)"}` } : undefined}
            >
              n/a
            </div>
          );
        }
        return (
          <div
            className="heat-cell"
            key={`${entry}-${exits[j]}`}
            title={`Entry ${fmtMult(entry)} / exit ${fmtMult(exits[j])} → IRR ${fmtPct(irr)}`}
            style={{
              background: irrColour(irr),
              color: irrTextColour(irr),
              outline: live ? "1.5px solid var(--text)" : undefined,
              fontWeight: live ? 600 : 400,
            }}
          >
            {fmtPct(irr, 0)}
          </div>
        );
      })}
    </>
  );
}

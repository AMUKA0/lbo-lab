/**
 * Formatting.
 *
 * The engine is unit-agnostic; the convention throughout the UI is that every
 * currency figure is in millions, so an entry EBITDA of 100 is $100m and the
 * enterprise value of 1,100 is $1.1bn. That is stated once on screen rather
 * than repeated as a suffix on every number.
 *
 * `null` means the engine could not produce a number (a failed structure, a
 * wiped-out sponsor, coverage with no interest). It renders as an em-dash. It
 * is never silently shown as zero.
 */

export const NA = "—";

const money0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const money1 = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function fmtMoney(value: number | null | undefined, dp: 0 | 1 = 0): string {
  if (value == null || !Number.isFinite(value)) return NA;
  const abs = Math.abs(value);
  const body = dp === 1 ? money1.format(abs) : money0.format(abs);
  return `${value < 0 ? "−" : ""}$${body}m`;
}

/** Signed, for bridge components where the direction is the point. */
export function fmtSigned(value: number | null | undefined, dp: 0 | 1 = 0): string {
  if (value == null || !Number.isFinite(value)) return NA;
  const formatted = fmtMoney(Math.abs(value), dp).replace("−", "");
  return `${value < 0 ? "−" : "+"}${formatted}`;
}

export function fmtPct(value: number | null | undefined, dp = 1): string {
  if (value == null || !Number.isFinite(value)) return NA;
  return `${(value * 100).toFixed(dp)}%`;
}

export function fmtBps(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return NA;
  return `${Math.round(value * 10000)}bps`;
}

export function fmtMult(value: number | null | undefined, dp = 1): string {
  if (value == null || !Number.isFinite(value)) return NA;
  return `${value.toFixed(dp)}×`;
}

export function fmtNum(value: number | null | undefined, dp = 1): string {
  if (value == null || !Number.isFinite(value)) return NA;
  return value.toFixed(dp);
}

/**
 * The IRR heat ramp: rust below the hurdle, neutral around it, pine above.
 *
 * Anchored on a 20% hurdle rather than on the range of whatever happens to be
 * in the grid — a relative ramp would repaint the same IRR a different colour
 * as the deal changes, which teaches the eye nothing.
 */
export function irrColour(irr: number | null): string {
  if (irr == null || !Number.isFinite(irr)) return "var(--edge-soft)";
  const lo = 0.0;
  const hi = 0.4;
  const t = Math.max(0, Math.min(1, (irr - lo) / (hi - lo)));
  if (t < 0.5) {
    // rust → neutral
    const k = t / 0.5;
    return `rgba(192, 101, 60, ${(0.85 - k * 0.7).toFixed(3)})`;
  }
  const k = (t - 0.5) / 0.5;
  return `rgba(70, 181, 129, ${(0.12 + k * 0.72).toFixed(3)})`;
}

/** Readable text on top of the ramp above. */
export function irrTextColour(irr: number | null): string {
  if (irr == null || !Number.isFinite(irr)) return "var(--text-3)";
  return irr > 0.28 || irr < 0.06 ? "#0b100e" : "var(--text)";
}

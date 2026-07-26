/**
 * Chart colours as literals.
 *
 * These duplicate the CSS custom properties in `styles/global.css` on purpose:
 * Recharts writes its colours out as SVG *presentation attributes*, and
 * `fill="var(--pine)"` does not resolve in an attribute the way it would in a
 * stylesheet. The two lists must be changed together — that is the cost of
 * using a chart library that doesn't emit classes.
 */

export const C = {
  pine: "#46b581",
  pineDeep: "#1f7a51",
  pineFaint: "rgba(70, 181, 129, 0.16)",
  brass: "#cf9c4c",
  brassDeep: "#8f6a2f",
  rust: "#c0653c",
  text: "#e9eae3",
  text2: "#a8b2ab",
  text3: "#6f7d75",
  edge: "#243029",
  edgeSoft: "#1b241e",
  raise: "#141b17",
  ink: "#0b100e",
} as const;

/**
 * Tranche colours, senior → junior, deliberately ordered light-to-dark within
 * the same hue family so the capital structure reads as a stack rather than as
 * unrelated categories. Cash and the revolver sit outside that family because
 * they are not term debt.
 */
export const TRANCHE_COLOURS = ["#46b581", "#2f8f66", "#1f6b4c", "#175139", "#0f3a28"];
export const REVOLVER_COLOUR = "#cf9c4c";
export const CASH_COLOUR = "#3f5d72";

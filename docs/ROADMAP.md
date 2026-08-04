# Roadmap

What is planned, what is deliberately not, and the reasoning behind both. Kept
because a decision without its reasoning gets re-litigated or silently reversed.

Current state: **308 tests**, deployed on Cloud Run, source public.

---

## Done

**The engine.** Sources & uses with equity as the plug, multi-tranche waterfall,
senior-first cash sweep, PIK accretion, NOL carryforwards, revolver, and the
interest ↔ balance circularity solved iteratively to 1e-10. Golden case solved by
hand. Mid-hold capital events: dividend recaps, divestitures, sponsor support
(equity cure / repurchase below par / debt-for-equity conversion), PIK toggles.

**The case-study library.** Four deals — Hilton, HCA, TXU, RJR Nabisco — each
modelled twice, from pre-close information and from the operating path that
happened, against the reported outcome.

**Excel, phases 1 and 2.** A live formula-driven workbook, tested against the
engine by independent recalculation; and the round trip back in via named ranges.

**A forward-looking PIK election.** The toggle is no longer a last resort fired
once the revolver is already exhausted. `pik_election_headroom` makes the
borrower look a year ahead and accrue at the junior rate rather than burn the
last of a facility at the senior rate; a coverage covenant is also a reason to
elect, and a leverage covenant deliberately is not, because PIK accretes to
principal and makes leverage worse.

*One review claim did not survive the numbers.* The finding said the greedy
election was load-bearing on TXU. It is not: the toggle strip is 0.38 of a 6.87-
turn structure, so electing it early saves a couple of hundred million against a
multi-billion gap, and the realised column breaks in year five at every headroom
setting. The mechanic was worth building; the specific claim about TXU was wrong,
and is recorded here rather than quietly dropped.

**Covenants, maturity walls and interest on cash.** Failure is no longer
liquidity-only: a maintenance covenant breached while the borrower is still
paying every coupon, and principal falling due with no way to roll it, are
reported as distinct findings. Covenants default to off, because cov-lite is
what the market issued. Cash earns a deposit rate, inside the same circularity
as the debt.

**§163(j).** The interest deduction capped at 30% of adjusted taxable income,
ahead of the NOL, with the disallowed amount carrying forward indefinitely.
In the engine and in the workbook, where the recalculation test proves the two
agree. Off for every case study, all of which predate the 2017 Act.

---

## Phase 3 — not started

### 3.1 Case studies as live workbooks — done

All eight columns export, including the three that break: those come out as a
schedule up to the break, matching what the page shows. The file announces
itself on the Inputs sheet, and its Returns sheet refuses to print an IRR
rather than striking one on a balance sheet where no sale happened.

Exporting them found two real formula bugs, both invisible to every fixture the
suite had. The cash sweep double-counted whenever a *second* tranche was
sweepable — every existing fixture had exactly one — and the revolver was never
repaid from divestiture proceeds even though the tranche formulas already
assumed it had been, so RJR printed a billion of debt that was not there.

### 3.2 Print-ready output — done

Landscape and fit-to-width for the schedule, portrait for the narrow sheets,
repeating year headers, explicit print areas, and a footer carrying the sheet
name and page numbers. Fit-to-height is deliberately left at "as many pages as
it takes": forcing a long schedule onto one page shrinks the type until nobody
can read it, which is the usual way this gets done badly.

### 3.3 What "finished" requires

The project is a portfolio piece, so done means *defensible to a practitioner*,
not feature-complete. Three things separate the current state from that:

1. **A human has looked at it.** Nobody has. That is the cheapest and most
   overdue item on this list.
2. **Nothing on the page contradicts the code.** Two reviews found live prose
   asserting things the engine no longer did. Three tests now guard against that
   class of error — stale column notes, denied mechanics, and displayed bridge
   rows that do not sum — but the guards only cover what has already gone wrong
   once.
3. ~~**The honest limits are stated where a reader meets them**, not only in
   the README.~~ Done. `api/limitations.py` serves them, the simulator renders
   them with the direction each omission errs in, and a staleness guard rejects
   any entry denying a mechanic the engine has — with a test proving the guard
   fires, since a guard that cannot fail is decoration.

### 3.4 Concrete definition of done for Phase 3

- Case pages offer an Excel download, and the broken columns export up to the
  break rather than refusing outright.
- A test asserts an exported case workbook matches that case's published
  figures, so the two cannot drift.
- Print setup on every sheet.
- ~~The README's deployment section explains why the Dockerfile imports the app
  at build time.~~ Done.

---

## Open findings from the PE reviews

Two independent reviews found real errors; most were fixed (see git history).
These were not:

- **Selection bias in the library.** Four famous deals, three peak-vintage. Named
  in the README, but as a footnote when it is arguably the dominant limitation. A
  clean fifth case (Dollar General 2007 is the obvious candidate — same vintage,
  sane multiple, clean outcome) would fix it better than more prose.

---

## Deliberately not doing

**An Office.js add-in.** "Excel native" could mean a task pane inside Excel. It
is a separate project — Microsoft developer registration, a second JS codebase, a
review process — and buys little over a well-built workbook.

**Macros.** A `.xlsm` is blocked by most corporate security policies and reads as
untrustworthy on arrival. Everything here works in plain `.xlsx`.

**Monte Carlo.** It looks impressive and is usually hollow: the hard part is the
correlation structure between drivers, and independent draws produce confidently
wrong tails. Only worth building with an explicit correlation matrix and a stated
caveat.

**Quarterly periodicity and floating rates.** High effort, low signal. The README
explains why annual and fixed are the right screening conventions.

---

## Standing caveat

The site has never been reviewed at full width by a human, and never seen at all
by its author beyond an 800×343 pane. It is public. That should be fixed before
the link goes anywhere.

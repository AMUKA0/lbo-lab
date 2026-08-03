# Roadmap

What is planned, what is deliberately not, and the reasoning behind both. Kept
because a decision without its reasoning gets re-litigated or silently reversed.

Current state: **197 tests**, deployed on Cloud Run, source public.

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

---

## Phase 3 — not started

### 3.1 Case studies as live workbooks

The strongest remaining artefact: *"here is Hilton 2007 as an auditable Excel
model"* is a better thing to hand someone than a web page. Six of the eight case
columns already export; the two that don't are RJR's and TXU's realised paths,
which hit a liquidity break and so have no complete schedule.

Needs: a download control on the case page, and a decision about the two broken
columns — most likely export the schedule up to the break, matching how the web
page already shows a partial run.

*Also worth doing:* a test asserting the exported case workbook agrees with the
case's own published figures, so the site and the workbook cannot drift.

### 3.2 Print-ready output

An IC exhibit gets printed. Page setup, print areas, repeating header rows,
landscape orientation, sensible page breaks between sheets. Small, and the
absence of it reads as amateur the first time someone hits Ctrl-P.

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
3. **The honest limits are stated where a reader meets them**, not only in the
   README. The case pages do this; the simulator does not.

### 3.4 Concrete definition of done for Phase 3

- Case pages offer an Excel download, and the broken columns export up to the
  break rather than refusing outright.
- A test asserts an exported case workbook matches that case's published
  figures, so the two cannot drift.
- Print setup on every sheet.
- The README's deployment section explains why the Dockerfile imports the app at
  build time — a missing dependency once failed the deploy rather than the
  build, and the fix is only useful if the next person knows why it is there.
- §163(j) implemented, or removed from the "genuine gaps" list and stated as a
  deliberate exclusion with reasoning. Currently it sits in an uncomfortable
  middle: named as missing, which invites the question without answering it.

---

## Open findings from the PE reviews

Two independent reviews found real errors; most were fixed (see git history).
These were not:

- **§163(j) is absent.** The 30%-of-adjusted-taxable-income interest limitation
  binds harder on a levered deal than the §172(a) NOL rule that *is* implemented.
  The case studies all pre-date the 2017 Act so it does not affect them, but the
  simulator's default is a modern US LBO paying tax relief it would not get.
- **No covenant test and no maturity wall.** Failure is tested on liquidity only,
  which is the rarer of the real modes. Most 2008–09 sponsor distress was
  covenant-driven; TXU's actual death was a 2014 maturity wall.
- **The PIK election is greedy.** The engine toggles only when a year already
  fails, i.e. when the revolver is exhausted — so it will burn revolver capacity
  at the senior rate for two years rather than PIK at the junior rate earlier. A
  treasurer looking a year ahead decides differently. On TXU that choice is
  load-bearing.
- **No interest income on balance-sheet cash.** HCA's realised column carries
  $1.5bn earning nothing.
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

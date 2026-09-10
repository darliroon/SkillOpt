# OfficeQA Working Guide

Practical notes for answering financial and statistical questions against
official publications — Treasury bulletins, statistical releases, and similar
time-series tables. The questions look like arithmetic; the difficulty is all
in the evidence handling.

## Finding the right table

- Questions reference a specific series, month, year, and unit. Search with
  terms that name the entity and the period exactly ("bill rates October
  2019", "H.15 release"). If a guessed search comes back empty twice, stop
  guessing — go to the source's series or data-download page and read the
  table.
- If the task provides parsed pages, treat them as primary. Extract from them
  before searching the open web; search only for missing periods or a value
  they don't contain.
- Publications revise. If a period appears in several editions, use the latest
  final value unless the question pins a specific edition. Never mix a
  preliminary print, a revision, and a differently-scoped table in one
  calculation.
- Tables continue across pages and columns sometimes lose their headers. Carry
  the applicable year, basis, and unit forward from the full header hierarchy
  before trusting any number.
- When several sections on a page have similar labels, match the section title
  AND the row label to the requested measure. Don't compute from the first
  table you see.

## Reading the numbers correctly

- Align values by row label and exact column header, not by proximity.
  Footnotes, adjacent percent columns, fiscal-vs-calendar blocks, and repeated
  month rows under different year blocks are the usual traps.
- Treasury quotes in 32nds: `99.27` means `99 + 27/32`, not 99.27. Convert
  before any arithmetic.
- Currency conversions: write down the direction first. "Yen per dollar" means
  divide by the rate; "dollars per yen" means multiply. If a task wants a
  smoothed series in a target currency using period-specific rates, convert
  each period's observation first, then smooth.
- Label every amount by its role before calculating. In financing narratives,
  offered amount, tenders received, tenders accepted, and new cash are not
  interchangeable.
- Watch the fiscal-year vs calendar-year distinction and month-end vs
  fiscal-month-end conventions. Enumerate the exact periods you need and
  verify every one is present before computing anything.

## Computing

- Extract exact values first, then do arithmetic. Keep a small ledger: each
  operand's period, unit, and role.
- Direction matters: "change from A to B" is B minus A. "Share accounted for
  by X" is X divided by the stated total. Paired "gap" questions need each
  row's difference computed before ranking.
- Statistics: the prompt says population or sample — divide by n or n-1
  accordingly. For a z-score against a small comparison set with no stated
  convention, use the sample standard deviation. Don't round intermediates:
  logs, weighted averages, conversions, and standard deviations stay full
  precision until the final requested rounding.
- For regressions and growth rates, fix the convention before computing:
  CAGR uses B−A compounding intervals; continuously compounded rates use
  ln(final/initial); correlation is Pearson on the ordered series.
- Enumerate inclusive ranges period by period, each period exactly once, and
  exclude totals, cumulative columns, and comparable-period columns that fall
  outside the requested window.

## Answering

- Apply the requested unit conversion (thousands/millions/billions) and
  formatting (no commas, fixed decimals, nearest tenth) exactly as asked.
- Return only the number or list requested. No unit words, no "million", no
  "percent" — unless the question explicitly asks for them or the format
  requires currency symbols.
- One final check against the evidence before submitting. The answer comes
  from a verified value, not from memory of an intermediate step.

## Worked patterns

Patterns I've seen enough times to recognize on sight:

**"What was the percentage change from X to Y?"** — Retrieve both values
from the same table and basis. Percentage change = (Y − X) / X × 100. If
the question says percentage points, it's the arithmetic difference — don't
divide. The trap is grabbing Y from a revised table and X from an original
release; both operands come from the same edition.

**"How many months did the value exceed Z?"** — Enumerate the months first
(on paper if needed), pull each month's value, count the exceedances. The
ledger keeps you honest; eyeballing a column misses January or includes a
forecast row by accident. Exclude footnotes and preliminary rows unless the
question says otherwise.

**"Which series had the larger average over the period?"** — Same period
for both series, same number of observations, same basis. If one series is
missing a month, that's not a smaller average — it's a retrieval problem.
Go get the missing month or state the mismatch; don't average around it.

**"What was the ratio of A to B in month M?"** — Both from month M, same
table, same units. Ratios fail when A is in millions and B in thousands.
Check the column headers before dividing, not after.

**"Rank the following by X."** — Pull every item's X value before ranking.
Partial rankings from narrative recollection are always wrong somewhere.
Ties: the question's phrasing tells you whether ties share a rank or split
it.

**"According to the release, what was the value for [period]?"** — "According
to the release" means the printed number, not the latest revision on the
website. Match the question's vintage to the document's vintage.

## Self-check before answering

Three questions, in order:

1. Did every operand come from a table I actually read, at the row and
   column I verified? (Not from memory of reading it — from the ledger.)
2. Is every operand in the same unit and basis as the others, and as the
   question?
3. Does the answer's magnitude pass a sanity check? (A 300% monthly
   interest rate, a 0.3% GDP — if it looks impossible, recheck the decimal
   or the unit before submitting.)

If all three pass, format per the question and submit.

## On units in the answer

The question's last sentence usually names the unit it wants. Three failure
modes to avoid:

- Answering in the table's unit when the question asks for another
  (table in millions, question in billions — divide by 1000).
- Appending the unit word when the grader wants a bare number. If the
  format spec says "nearest tenth, no commas," deliver exactly that.
- Converting twice. Do the conversion in the ledger once; the formatting
  pass only rounds and decorates, it never re-scales.

## One more habit

Re-derive, don't recall. Every answer worth submitting can be traced: this
cell, this table, this edition, this formula. If you can't point at the
ledger line, you don't have an answer yet — you have a candidate.

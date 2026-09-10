# Trace2Skill: OfficeQA Execution Lessons

Lessons distilled from recorded OfficeQA execution traces, organized by stage
and recurring failure pattern.

## Retrieval Lessons

R1. Prefer targeted search terms that name the exact entity, period, measure,
or table concept from the question. Generic searches return noise that costs
steps.

R2. When an external official time-series observation is needed, prefer the
source's series/data-download/table page once identified. If exact-date or
guessed-value searches return empty results, stop repeating them; broaden to
the official series name/code plus `data` or `download` and read the table
values. Traces show repeated failed identical searches burning the budget.

R3. Treat provided/oracle parsed pages as primary evidence: if they contain
the relevant table and period, extract directly from them before searching
elsewhere; search only for missing continuation pages, missing periods, or an
official actual value not present.

R4. If the requested date range extends beyond the provided page, enumerate
the required periods first and verify every period is present in evidence.
Traces failed by computing from a partial ledger or filling missing periods
from memory. Retrieve continuation pages or a later issue containing the
missing dates/revisions.

R5. Start by narrowing to the most likely candidate file before reading long
passages. After a promising match, read only a small surrounding span and
verify it matches the requested year, basis, and unit.

## Table Alignment Lessons

A1. Align values by row label and exact column header, not proximity. Watch
for continued or unlabeled columns, footnotes, adjacent amount-vs-percent
columns, fiscal-year vs calendar-year sections, and repeated month rows under
different year blocks.

A2. When a page contains multiple sections with similar labels, use only the
section whose title and row label match the requested measure exactly. Failed
traces computed from the first visible table when the requested table was
absent or partial.

A3. Resolve abbreviated or inherited table labels from the full header
hierarchy before extraction; carry forward the applicable year, date,
category, and unit only when the table structure clearly establishes them.

A4. When a search term has multiple plausible matches, inspect each match's
surrounding table title, header hierarchy, date basis, unit, and row
semantics before selecting evidence; never use the first matching row solely
because its label matches.

## Computation Lessons

C1. Extract the exact value from the retrieved text before doing any
arithmetic; keep track of each operand's period, unit, and semantic role so
nearby proxy values are not mixed in.

C2. Preserve the direction and sign implied by the wording: "change from A to
B" means B minus A; "former than latter" means former minus latter; "share
accounted for by X" means X divided by the stated total; paired "gap"
questions require computing each within-row difference before ranking.

C3. For Treasury security quotations, obey the table's quote basis: if price
decimals are 32nds, convert `99.27` as `99 + 27/32`, not decimal `99.27`.

C4. For currency conversion, make a direction ledger first: source table
unit, source currency, exchange-rate orientation (foreign currency per U.S.
dollar means divide by the rate; U.S. dollars per foreign unit means
multiply), and requested final unit. For smoothing/averaging/forecasting in a
target currency with period-specific rates, convert each period's observation
first.

C5. For Treasury financing narratives, label each amount by transaction role
before calculating: offered amount, tenders/subscriptions received, tenders
accepted, competitive/noncompetitive accepted, foreign or Government-account
exchange tenders, refunding, and new cash are not interchangeable.

C6. For statistical, regression, correlation, and growth-rate questions,
write a formula ledger before calculating: confirm the exact series and
endpoints, ordered vector, elapsed intervals, and requested convention
(continuously compounded rate, CAGR, Pearson correlation, OLS index/year).

C7. If the prompt says population standard deviation, divide by `n`; if it
says sample, divide by `n-1`; for a z-score against a small comparison set
with no stated convention, use the sample standard deviation of the
comparison set.

C8. Do not round intermediate operands, weighted averages, logs,
exchange-rate conversions, or standard deviations before the final requested
rounding.

## Series Discipline Lessons

S1. When a requested period appears in multiple editions or table variants,
identify the exact requested table and measure first, then use the latest
final/revised observation unless the question explicitly fixes an edition.
Reconcile overlapping values before calculation.

S2. For inclusive time-series ranges, make a period-by-period ledger covering
every requested month/year exactly once; exclude totals, cumulative-to-date
columns, comparable-period columns, estimates, and extra latest-month columns
outside the requested range.

S3. For multi-stage questions where one table determines the period/entity
used in another lookup, freeze that derived key with evidence first, then
retrieve the second measure only for that exact month/year/reporting
date/entity.

## Output Lessons

O1. Enforce the requested unit and format before finalizing: convert
thousands/millions/billions or full nominal dollars as needed, then apply
no-comma, fixed-decimal, whole-number, or nearest-tenth/thousandth formatting
exactly as asked.

O2. Unless the prompt explicitly asks for unit words or explanatory text,
return only the numeric value or requested list; do not append words such as
`million`, `dollars`, `percent`, or `percentage points`.

O3. Return the final answer only after one last consistency check against the
retrieved evidence; copy the final answer from a checked value, not from an
unverified intermediate guess.

O4. When the question spans multiple candidate files, periods, or dates,
retrieve and verify the corresponding table independently in every required
file before combining values; align each result by heading, date basis, row
category, and unit.

## Consolidated Observations

X1. The dominant failure classes in traces: partial-period ledgers (R4),
proximity-based table alignment (A1), and unit/direction errors in derived
quantities (C2, C4). Fixing these three covers most lost points.

X2. Verification habit: re-derive the final number from the ledger, not from
the narrative, before formatting.

## Additional Lessons (Later Batches)

B1. Before computing any percentage change, confirm whether the question
asks for percent change — (Y − X) / X — or percentage points — the
arithmetic difference. Traces conflated the two on visually similar
questions.

B2. For "how many months exceeded Z" counting questions, enumerate the
months in a ledger first, then count; eyeballed counts missed boundary
months or included footnote rows.

B3. For ratio questions, verify both operands share the same table, month,
and unit before dividing; mixed scales (millions vs thousands) produced
1000-fold errors.

B4. "According to the release" phrasing pins the answer to the printed
vintage, not the latest revision on the website.

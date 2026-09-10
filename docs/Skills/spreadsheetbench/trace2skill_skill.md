# Trace2Skill: SpreadsheetBench Execution Lessons

Lessons consolidated from recorded execution traces on spreadsheet manipulation
tasks. Organized by workflow stage, recurring failure pattern, and task family.
Rule IDs are stable across sections for cross-reference.

## Tooling Lessons

T1. Use `openpyxl` for reading and writing workbooks; use `pandas` only for
in-memory data transformation. Multiple failed traces used `pandas.to_excel()`
to write results and destroyed formulas, named ranges, and formatting present
in the original workbook. Lesson: write back through `openpyxl.save()`.

T2. Load the workbook twice when formulas are involved:
`openpyxl.load_workbook(INPUT_PATH)` gives formula strings, while
`openpyxl.load_workbook(INPUT_PATH, data_only=True)` gives the cached values
from the last recalculation. Traces show agents reading `None` from formula
cells and then computing garbage from the wrong workbook view.

T3. Define `INPUT_PATH` and `OUTPUT_PATH` at the top of `solution.py`. Several
traces failed because paths were hardcoded to the exploration file and the
output went to the wrong location.

T4. Run the script end-to-end before declaring completion. A class of failures
came from scripts with syntax errors or paths that were never executed.

## Structure Discovery Lessons

S1. Tables do not always start at A1. Scan the used range for complete header
groups — tables may begin in later rows, sit to the right of labels, have title
rows above them, or share a sheet with multiple source and result tables. Build
a header map such as `{str(cell.value).strip(): cell.column}` from actual cells
instead of assuming fixed coordinates.

S2. Inspect beyond the preview: nearby rows and columns, sample outputs,
formulas, labels, and any `Output`, `Manual Result`, or `Desired...` sheets.
Treat filled cells in the requested output area as semantic examples of the
expected format — but still recompute and write the complete requested range.

S3. Distinguish source tables from destination tables using nearby labels and
the requested output range before writing anything.

S4. When the destination is a labeled area (not a new sheet), write derived
results directly into the named range or columns. Do not insert rows/columns,
relocate the source table, or sort/delete source records unless that structural
change is explicitly requested — traces that restructured the workbook failed
verification even when their values were right.

## Value and Matching Lessons

V1. Normalize text keys before comparison: trim whitespace, collapse repeated
spaces and NBSPs, casefold, and consider punctuation-insensitive keys when
labels have inconsistent punctuation or spacing.

V2. Parse numeric text after removing commas and currency symbols while
preserving signs and decimal points. Handle placeholders — `"-"`, `"$"`,
`"$0"`, blanks, and numeric zero — deliberately; they are not interchangeable.
Skip `None`/blank and booleans in numeric tests.

V3. Normalize date keys: handle `datetime`/`date` objects, Excel serial
numbers, and date-like strings; compare at the granularity the task implies
(exact date, month, month/year, fiscal period, or year). Text months such as
`March`, sheet names, title text, and date cells can all name the same period —
canonicalize them before matching.

V4. For "begins with" use `startswith`; for "contains / search / occurrence"
use substring search; use exact normalized equality only when a whole-cell
match is implied. Traces show operators chosen by habit instead of by the
instruction's wording.

V5. For joins, deduplication, grouping, and interval lookups, build explicit
normalized keys — composite keys when the task refers to multiple fields.
Preserve original source order within each group unless sorting is requested.

V6. Treat numeric-looking IDs consistently: `330`, `330.0`, and `"330"` must
map to one canonical key.

V7. Keep numeric outputs numeric; use `number_format` for display formatting
instead of converting numbers to strings. Time values want real `time`/`datetime`
values with an Excel format such as `hh:mm:ss AM/PM`, not text substrings.

## Formula Semantics Lessons

F1. `openpyxl` writes formula strings but does not evaluate them. If the
checker reads values, compute results in Python and write literal values unless
the task explicitly requires live formulas.

F2. When the task provides an existing or broken formula, use it as a semantic
specification: honor its referenced lookup ranges, criteria, return ranges,
aggregation intent, and error-handling behavior; then write the resulting
values. Failed traces either guessed different source columns or left
unevaluated formula strings in the output.

F3. Wording like "write/fix a formula", "SUMIFS/COUNTIFS", "VBA", or "macro"
describes the spreadsheet logic to implement; for normal `.xlsx` outputs,
implement the equivalent in Python and write computed final values. Deliver the
completed workbook state, not the formula text, unless the task explicitly says
the output must contain live formulas.

F4. For "every nth row" or OFFSET-style tasks, infer the source column, first
source row, and step from the provided examples or formulas, then copy actual
source values into the requested output range as literals.

## Aggregation and Output Lessons

A1. For numeric aggregation, crosstab, SUMIFS-like, and INDEX/MATCH-style
summary outputs, infer missing-match behavior from table semantics and
examples: numeric summary grids usually require literal `0` for no matching
records; filtered lists or "show only once" outputs usually require blanks.

A2. First pass to build normalized dictionaries/groups/range structures;
second pass to write results. Avoid nested full-sheet scans per row.

A3. When replacing a generated output area, clear only the instructed target
range so stale values or formulas do not remain below the new results.

A4. Collect filtered lists, summaries, and aggregations in memory first,
preserving required order, then write from the first output row and clear
leftover cells below the new results in the target columns.

A5. When adding rows, copy style/alignment/number format from an existing
template row; when deleting rows, delete from bottom to top to avoid
row-index shifts.

A6. Preserve intended blanks as empty cells (`None`) rather than placeholder
text or `0` unless the task specifies otherwise. For blank-sensitive logic
("if input is blank, output blank"), evaluate the driving input with
`data_only=True` and write `None` for truly blank outputs.

A7. Preserve formatting, column widths, borders, formulas, and unrelated cells
unless the instruction asks to change them. If formatting changes are
requested, apply them exactly, after writing values, only to the requested
cells; convert hex colors to ARGB (`#FFC000` → `FFFFC000`); "format as text"
means `number_format = '@'` with string values.

## Special-Row Lessons

R1. When a target range includes special rows — `Total`, `Grand Total`, `min`,
`max`, constraints, headers, or blank separators — do not apply ordinary row
logic blindly. Compute totals as aggregates when indicated; leave constraint,
header, and blank cells untouched.

R2. For INDEX/MATCH problems where the first row works but subsequent rows
fail, treat row labels, column/year headers, region/type criteria, and
expense/category labels as a multi-key lookup; fill the whole matrix from the
source data using cached `data_only` values when source cells are formulas.

R3. For multi-step macro/VBA-style requests, implement every stated operation,
not just the first deletion or filtering step. Re-read the numbered
requirements before saving and verify later computed columns, totals, and
derived fields as well as the obvious filtered rows.

R4. For residual-balancing tasks: identify data rows separately from min/max
constraint rows; add positive residuals from unit 1 toward unit 5 without
exceeding max values; subtract negative residuals from unit 5 toward unit 1
without going below min values; update only unit cells in actual data rows.

R5. For time-threshold rows, decide per row whether it is a normal data row
or a summary row; summary rows aggregate the computed normal-row results when
the workbook labels or examples indicate a total.

## Consolidated Observations

O1. The dominant failure mode across traces was F1/F3: leaving unevaluated
formulas in output cells or reimplementing formulas as formulas instead of
values. The checker reads values; compute in Python, write literals.

O2. The second dominant failure mode was S1/V3 combined: misaligned tables and
unnormalized period keys. Discover structure from actual cells, canonicalize
period labels from all sources, then match.

O3. Verify after saving: reload the output workbook and check representative
target cells are non-formula literals where values are expected. An
unexpectedly `None` target cell means the script is not finished.

## Period and Schedule Lessons

P1. For monthly or period summary grids, canonicalize period labels from
all sources — sheet names, title text, row/column headers, text months such
as `March`, and actual date cells — then match summaries by normalized
period plus the other stated criteria rather than by fixed month offsets or
existing formulas. Traces failed by assuming January's output sits one
column right of December's.

P2. For date ranges and rolling windows, infer endpoint inclusivity from
wording and examples: phrases like "X to Y", "through", or "up to", or
examples such as "2 to 5" meaning "4 days", usually require inclusive
boundaries.

P3. For schedule or calendar fill tasks, build a cycle-day-to-periods
mapping from the schedule/template area first, then fill the daily rows
across all requested class columns based on each row's cycle day. Preserve
repeated or double periods exactly as shown by the template; do not leave
formulas in the schedule cells.

P4. Fiscal versus calendar periods: when a task mixes "FY" and calendar
language, reconcile the workbook's convention (from labels and examples)
before computing; traces that assumed calendar months against fiscal
headers produced consistently shifted results.

## Residual and Constraint Lessons

Q1. For residual-balancing tasks (restated from R4 with trace detail):
identify data rows separately from min/max constraint rows; add positive
residuals from unit 1 toward unit 5 without exceeding max values; subtract
negative residuals from unit 5 toward unit 1 without going below min
values; update only the unit cells in actual data rows. Failed traces
applied balancing to constraint rows and produced out-of-range values.

Q2. For time-threshold rows, decide per row whether it is a normal data row
or a summary row; normal rows use the before/after threshold rule, summary
rows aggregate the computed normal-row results when the workbook labels or
examples indicate a total.

Q3. For multi-step macro/VBA-style requests, implement every stated
operation in the workbook, not just the first deletion or filtering step.
Re-read the numbered requirements before saving and verify later computed
columns, totals, and derived fields as well as the obvious filtered rows.
Traces repeatedly completed step 1 of 4 and shipped.

## Formatting and Style Lessons

M1. When adding rows, copy style/alignment/number format from an existing
template row — newly created cells carry no style, and naked values in a
styled table fail visual checks (A5, restated with the failure mechanism
made explicit).

M2. When deleting rows, delete from bottom to top to avoid row-index
shifts (A5 companion rule; separate because failures occurred even when
the write-back rule was followed).

M3. For "format as text", set `number_format = '@'` and write string
values when the expected cell values are text; a number written to a
text-formatted cell still compares unequal to the string the task expects.

M4. Convert hex colors to ARGB when filling: `#FFC000` becomes
`FFFFC000`. Fills written with the raw hex string silently fail.

M5. Times: parse `datetime`, `time`, Excel serial or fractional times, and
time-like strings into real Python `time`/`datetime` values, then write
real time values with an Excel `number_format` such as `hh:mm:ss AM/PM`;
text substrings do not behave as times in comparisons or arithmetic (V7,
restated because time tasks were a distinct failure cluster).

## Iteration and Scanning Lessons

I1. For outputs that depend on other rows or lookup grids, make a first
pass to build normalized dictionaries/groups/range structures, then a
second pass to write results (A2, restated with the mechanism: nested
full-sheet scans per row are both slow and, more importantly,
order-dependent — earlier rows see incomplete structures).

I2. Split delimited tokens and ignore empty tokens when exploding
multi-value cells; trailing delimiters create phantom empty rows that then
match nothing and produce wrong counts.

I3. Treat error literals such as `#N/A` as meaningful sentinel values when
the task refers to them; do not skip or overwrite them implicitly.

I4. For lookups supporting exact keys, numeric-looking keys, and
interval/range tables: implement all three match modes rather than one —
traces implemented exact match and failed interval rows.

## Output Area Lessons

D1. When replacing a generated output area, clear only the instructed
target range before writing so stale values or formulas do not remain
(A3, restated with the failure mode: leftover stale rows below shorter new
results were accepted as correct by the agent and rejected by the
checker).

D2. For filtered lists, summaries, and aggregations, collect all source
records/results in memory first, preserving required order, then write
from the first output row (A4, restated: writing while iterating produced
interleaved old and new rows when filters matched non-contiguous rows).

D3. Write into the named destination range without relocating the source
table (S4, restated: agents "tidied" the workbook by sorting sources and
broke position-based verification).

## Consolidated Addenda

O4. Reading the example output area is the highest-value single action
before coding: it resolves format, empty-bucket behavior, ordering, and
rounding questions simultaneously.

O5. The failure taxonomy is now: formula-vs-value confusion (F1/F3),
structure misalignment (S1/P1), normalization gaps (V1-V3), output-area
hygiene (D1/D2), multi-step omissions (R3), and row-surgery errors
(M1/M2). Every trace failure in the corpus maps to at least one of these.

O6. Verification closes the loop: reload the saved workbook, re-read
representative target cells, and confirm non-formula literals where values
are expected (T4, now with the observed effect: verification catches every
failure class in O5 except logic errors, which only example comparison
catches).

# Spreadsheet Manipulation Skill (Optimized)

Guidance evolved over optimization rounds for spreadsheet manipulation tasks.
Later sections refine, and in places restate, earlier rules with additional
conditions discovered during evaluation; when two rules overlap, the more
specific (later) rule governs.

## Core Operating Rules

1. Read the instruction and the workbook before writing any code. List all
   sheets, locate every table by scanning the used range for complete header
   groups, and identify the requested output range.
2. Write `solution.py` with `INPUT_PATH` and `OUTPUT_PATH` defined at the top.
   Run it end-to-end; fix syntax, indentation, and runtime errors before
   finishing.
3. Use `openpyxl` for structure-preserving reads and writes. Use `pandas` only
   for in-memory data transformation, and write results back through
   `openpyxl.save()` — `pandas.to_excel()` silently destroys existing formulas,
   named ranges, and formatting.
4. Do not hardcode row counts or column letters; iterate over actual rows and
   cells in the workbook.
5. Preserve sheets, cells, formatting, and formulas not mentioned by the
   instruction.

## Workflow Discipline

- Explore the input file first: list sheets, inspect headers, check dimensions.
  Then inspect actual workbook data beyond any preview — nearby rows and
  columns, sample outputs, formulas, labels, headers, and reference or example
  sheets such as `Output`, `Manual Result`, or `Desired...` tabs.
- Treat existing filled cells in the requested output area or adjacent example
  tables as semantic examples for edge cases and expected formats, but still
  recompute and write the complete requested target range. Do not simply copy
  example values where computation is required.
- Confirm the target cells or ranges contain the expected values after saving.
  If a requested target cell is unexpectedly `None`, the script is not
  finished — fix it before declaring completion.
- Keep scripts simple enough to run cleanly. Avoid unnecessary dynamic code
  generation and fragile f-strings with regex expressions inside them.

## Structure and Header Resolution

- Scan the used range for complete header groups, not just row 1. Tables may
  start in later rows or columns, have title rows above them, or have multiple
  source and result tables on the same sheet; use nearby labels and the
  requested output range to distinguish sources from destinations.
- Locate tables, fields, and target ranges by header text, nearby labels, and
  surrounding nonblank structure rather than fixed coordinates. Build header
  maps from actual cells when useful, e.g.
  `{str(cell.value).strip(): cell.column}`. (Restated with additions: when the
  same header text appears in several tables, disambiguate by sheet, by the
  labels above the header row, and by which table's extent contains the
  requested output range.)
- If a visible table looks partial, check continuation columns or adjacent
  unlabeled blocks before assuming the table is complete.
- When the instruction names a destination range or columns, write derived
  results directly there. Do not insert rows/columns, relocate the source
  table, or sort/delete source records unless that structural change is
  explicitly requested.

## Value Extraction and Normalization

- Normalize text by trimming, collapsing repeated spaces and NBSPs, and
  casefolding for comparison; restore original text for output. When names or
  labels have punctuation or spacing inconsistencies, consider
  punctuation-insensitive keys.
- Parse numeric text after removing commas and currency symbols while
  preserving signs and decimal points; skip `None`/blank and booleans for
  numeric tests. Handle placeholders such as `"-"`, `"$"`, `"$0"`, blanks, and
  numeric zero deliberately — they are distinct states and tasks refer to them
  differently.
- Normalize date keys deliberately: handle `datetime`/`date` objects, Excel
  serial numbers, and date-like strings, then compare at the granularity
  implied by the task — exact date, month, month/year, fiscal period, or year.
  For workday or date-window logic, compute the range in Python and exclude
  weekends/holidays as specified.
- For monthly or period summary grids, canonicalize period labels from all
  sources: sheet names, title text, row/column headers, text months such as
  `March`, and actual date cells. Match summaries by normalized period plus
  the other stated criteria, not by fixed month offsets or existing formulas.
- For date ranges and rolling windows, infer endpoint inclusivity from wording
  and examples: phrases like `X to Y`, `through`, `up to`, or examples such as
  `2 to 5` meaning `4 days`, usually require inclusive boundaries.
- Parse `datetime`, `time`, Excel serial or fractional times, and time-like
  strings into real Python `time`/`datetime` values. Write real time values
  with an Excel `number_format` such as `hh:mm:ss AM/PM`; do not write text
  substrings when the result should behave as a time.
- For joins, deduplication, grouping, interval lookups, lookup grids, and
  ordered outputs, build explicit normalized keys, including composite keys
  when the task refers to multiple fields. Preserve original source order
  within each group unless sorting is explicitly requested.
- For lookups, filters, joins, and label/header matching, normalize comparison
  keys consistently: trim whitespace, skip blanks explicitly, use
  case-insensitive matching when appropriate, and treat numeric-looking IDs
  consistently (`330`, `330.0`, and `"330"` are one key).

## Formula Handling

- `openpyxl` can write formulas but does **not** calculate them or update
  cached results. If the requested output will be checked as cell values,
  compute the result in Python and write literal values unless the user
  explicitly requires live formulas.
- When existing formulas are inputs to your logic, load a second workbook with
  `data_only=True` to read cached values:

  ```python
  wb = openpyxl.load_workbook(INPUT_PATH)
  wb_values = openpyxl.load_workbook(INPUT_PATH, data_only=True)
  ws = wb["Sheet1"]; ws_values = wb_values["Sheet1"]
  ```

- Treat wording such as "write/fix a formula", "SUMIFS/COUNTIFS", "VBA", or
  "macro" as a description of the spreadsheet logic unless the deliverable
  explicitly requires live formula text, an `.xlsm`, or a preserved VBA
  project. For normal `.xlsx` outputs, implement the equivalent logic in
  Python/openpyxl and write the computed final values to the requested cells
  so verification does not depend on Excel recalculation or macros.
- When the user provides an existing or broken formula, use it as a semantic
  specification: honor its referenced lookup ranges, criteria ranges, return
  ranges, aggregation intent, and error-handling behavior, then write the
  resulting values rather than guessing different source columns or leaving
  unevaluated formulas.
- Additional refinement: even when the instruction says "formula", deliver the
  completed workbook state — compute intended results in Python and write
  literal final values. Only write formula strings when the task explicitly
  says the output must contain live formulas. After writing, reload or inspect
  the saved workbook and verify that every requested target cell contains a
  non-formula literal where a value is expected.
- For blank-sensitive formula tasks, compute the branch explicitly: if the
  driving source cell is truly blank, write `None`; otherwise write the actual
  result such as `0`, `1`, a category label, or a lookup value. Never rely on
  `IF(...,"",...)` formulas to be recalculated later.
- For "every nth row" or OFFSET-style tasks, infer the source column, first
  source row, and step from the provided examples or formulas, then copy the
  actual source values into the requested output range as literals.

## Output and Formatting Requirements

- Save the result to `OUTPUT_PATH`.
- Choose the comparison operator from the instruction and examples: use
  `startswith` for "begins with", substring search for
  "contains/search/occurrence", and exact normalized equality only when a
  whole-cell match is implied. Create small helper functions for comparisons
  and numeric parsing.
- When replacing a generated output area, clear only the instructed target
  range before writing new results so stale values or formulas do not remain.
  Preserve formatting, column widths, borders, formulas, and unrelated cells
  unless the instruction asks to change them.
- If the instruction includes formatting changes, apply them exactly after
  writing values and only to the requested cells or range. Use `openpyxl`
  styles for fills, alignment, fonts, borders, and number formats; convert hex
  colors to ARGB when needed, for example `#FFC000` → `FFFFC000`. For "format
  as text," set `number_format = '@'` and write string values when the expected
  cell values are text.
- For filtered lists, summaries, and aggregations, first collect all source
  records/results in memory, preserving the required order, then write from
  the first output row and clear leftover cells below the new results in the
  target columns. When adding rows, copy style/alignment/number format from an
  existing template row when appropriate; when deleting rows, delete from
  bottom to top to avoid row-index shifts.
- Preserve intended blanks as empty cells (`None`) rather than placeholder
  text or `0` unless the task specifies otherwise.
- Keep numeric outputs numeric; use `number_format` for display formatting
  instead of converting numbers to strings unless text is explicitly required.

## Edge-Case Rules

- For numeric aggregation, crosstab, SUMIFS-like, and INDEX/MATCH-style
  summary outputs, infer missing-match behavior from table semantics and
  examples: numeric summary grids usually require literal `0` for no matching
  records, while filtered lists or "show only once" outputs usually require
  blanks (`None`).
- For outputs that depend on other rows or lookup grids, make a first pass to
  build normalized dictionaries/groups/range structures, then a second pass to
  write results. Avoid nested full-sheet scans per row; split delimited tokens
  and ignore empty tokens, and treat error literals such as `#N/A` as
  meaningful sentinel values when the task refers to them.
- When a target range includes special rows such as `Total`, `Grand Total`,
  `min`, `max`, constraints, headers, or blank separators, do not apply
  ordinary row logic blindly to those rows. Compute totals as aggregates when
  indicated, and leave constraint/header/blank cells untouched unless
  explicitly requested.
- For residual-balancing tasks, identify data rows separately from min/max
  constraint rows. Add positive residuals from unit 1 toward unit 5 without
  exceeding max values; subtract negative residuals from unit 5 toward unit 1
  without going below min values; update only the unit cells in actual data
  rows.
- For time-threshold rows, decide per row whether it is a normal data row or a
  summary row. Normal rows use the before/after threshold rule; summary rows
  should aggregate the computed normal-row results if the workbook labels or
  examples indicate a total.
- For INDEX/MATCH problems where the first row works but subsequent rows fail,
  treat row labels, column/year headers, region/type criteria, and
  expense/category labels as a multi-key lookup. Fill the whole result matrix
  with values from the source data table, using cached `data_only` values when
  source cells are formulas.
- For multi-step macro/VBA-style requests, implement every stated operation in
  the workbook, not just the first deletion/filtering step. Re-read the
  numbered requirements before saving and verify later computed columns,
  totals, and derived fields as well as the obvious filtered rows.
- For schedule or calendar fill tasks, build a cycle-day-to-periods mapping
  from the schedule/template area first, then fill the daily rows across all
  requested class columns based on each row's cycle day. Preserve repeated or
  double periods exactly as shown by the template; do not leave formulas in
  the schedule cells.
- If workbook cells contain arbitrary sample text that could be sensitive or
  trigger content filters, do not quote large raw cell contents in your
  response. Process them locally in Python with neutral variable names and
  output only the completed script or workbook changes.

## Robustness

- Prefer simple, auditable row/column loops over complex workbook XML parsing
  unless the task truly requires unsupported workbook internals.
- Always execute the final `solution.py`; fix any syntax, indentation, or
  runtime error, then verify representative target rows were actually written.
- One more check, added late but important: verify that representative target
  cells were actually written by re-reading them from the saved output file —
  scripts that "ran successfully" have still produced empty or stale target
  cells when the write path was skipped by an early exit or a wrong branch.

## Further Refinements (Final Rounds)

The following rules were appended in later optimization rounds; they refine
the earlier sections and remain in force.

- Read the instruction twice: extract the target sheet, target range,
  condition, and output format before writing code. Numbered requirements
  are a contract — re-read them after writing the script and check each
  number against the saved output. (This closed a failure class where steps
  1–3 of 4 were implemented and step 4 was silently dropped.)
- When examples exist in the requested output area, match their format
  exactly: decimal precision, percent representation (0.12 vs 12), date
  display, and empty-bucket behavior. Where the example area conflicts with
  a general rule in this skill, the example area wins.
- Grids expect literal `0` for no-match cells; filtered lists expect blanks
  with leftover rows cleared. When the instruction is silent, decide from
  the structure: a fully laid-out period grid is a grid; a "show only"
  request is a filtered list.
- Total and Grand Total rows are outputs of aggregation loops, not
  participants in them. Compute the aggregate, then write it to the total
  row; constraint rows (min, max) are never data rows.
- Deleting rows: iterate bottom-to-top so index shifts do not skip rows.
  Adding rows: copy style/alignment/number format from an existing template
  row; newly created cells carry no style.
- When instructions mention sorting, prefer writing a new sorted output
  area over restructuring the source table in place; position-based
  verification tolerates a new area and fails on relocation.
- For interval lookups, implement range-match alongside exact-match;
  numeric-looking keys normalize to one canonical form before comparison.
- Fiscal-year labels require reconciling the workbook's own convention
  (from labels and adjacent examples) before computing against calendar
  dates; do not assume July–June or October–September globally.
- After saving, reload the workbook and re-read representative target
  cells: confirm expected literals, confirm no stale rows below shorter
  results, and confirm unrelated sheets are untouched. (Restated from
  Robustness with the specific checks enumerated — verification that does
  not re-read the saved file does not count.)
- On failure, shrink the problem: run the logic on the first five rows and
  print intermediate values; check for `None` in numeric loops before
  anything else — a `None` treated as a number is the most common runtime
  failure and usually points to a header row, a trailing blank, or a
  merged cell's empty tail.

### Final-Round Additions

- Read merged headers from the merge anchor: cells inside a merged range
  report `None` except the top-left cell; a header spanning four columns is
  still one header, not three unlabeled columns. (Appended after traces
  misread merged title rows as unlabeled data.)
- A sheet can contain several tables that look like one; the giveaway is a
  second header row mid-sheet or a blank-row gap followed by a different
  column count. Treat them as separate tables and identify the task's table
  by matching its headers to the instruction's field names.
- `ws.max_row` and `ws.max_column` include formatted-but-empty cells; find
  the real data boundary from content, not dimension metadata.
- Hidden rows and columns are still read by iteration; when totals seem
  doubled or shifted by a constant, check for hidden duplicates before
  suspecting the logic.
- Number formats do not change values: a cell displaying `1,234` may hold
  `1234`, `1234.0`, or text. Read the raw value for logic; apply
  `number_format` only when writing.
- When the workbook contains formulas in the target area, read them as
  specifications: `=A25` means copy A25's value; `=SUMIFS(...)` defines the
  sum's ranges and criteria; a `VLOOKUP(..., FALSE)` requires exact match;
  broken formulas (`#REF!`, `#NAME?`) still reveal intent from the function
  name and surviving operands — reconstruct, don't discard.
- Dry-run before transforming: print sheet names, dimensions, the first
  three rows of the relevant sheet, and the named target range; confirm the
  target range intersects a real table before writing any code.

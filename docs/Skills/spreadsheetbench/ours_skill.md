# Spreadsheet Manipulation Skill (xlsx)

## Overview
This skill guides agents in manipulating Excel (.xlsx) spreadsheets using Python.

**Primary libraries**: `openpyxl` (structure-preserving read/write), `pandas`
(data transformation). Never use any other third-party libraries.

## Common Workflow

1. **Explore** the input file: list sheets, inspect headers, check dimensions.
   Inspect actual workbook data beyond the preview, including nearby
   rows/columns, sample outputs, formulas, labels, and any reference or example
   sheets such as `Output`, `Manual Result`, or `Desired...` tabs. Treat
   existing filled cells in the requested output area as semantic examples for
   edge cases and expected formats, but still recompute and write the complete
   requested target range.
   Scan the used range for complete header groups, not just row 1. Tables may
   start in later rows/columns, have title rows above them, or hold multiple
   source/result tables on the same sheet; use nearby labels and the requested
   output range to distinguish sources from destinations. Locate tables and
   target ranges by header text and surrounding nonblank structure rather than
   fixed coordinates; build header maps from actual cells when useful, e.g.
   `{str(cell.value).strip(): cell.column}`.
2. **Write `solution.py`** with `INPUT_PATH` and `OUTPUT_PATH` defined at the
   top.
3. **Execute** `python solution.py` and verify the output file was created.
4. **Confirm** the target cells/range contain the expected values; if a
   requested cell is unexpectedly `None`, fix the script before finishing.

## Library Selection

| Use case | Library |
|----------|---------|
| Preserve formulas, formatting, named ranges | `openpyxl` |
| Bulk data transformation, aggregation, sorting | `pandas` → write back with `openpyxl` |
| Simple cell read/write | `openpyxl` |

**Warning**: `pandas.to_excel()` silently destroys existing formulas and named
ranges. When writing back to a spreadsheet that contains formulas, always use
`openpyxl.save()`.

**Formula evaluation caution**: `openpyxl` can write formulas but does **not**
calculate them or update cached results. If the requested output will be
checked as cell values, compute the result in Python and write literal values
unless the user explicitly requires live formulas. When existing formulas are
inputs to your logic, load a second workbook with `data_only=True` to read
cached values while saving changes through the normal workbook:

```python
wb = openpyxl.load_workbook(INPUT_PATH)
wb_values = openpyxl.load_workbook(INPUT_PATH, data_only=True)
ws = wb["Sheet1"]; ws_values = wb_values["Sheet1"]
```

Treat wording such as "write/fix a formula", "SUMIFS/COUNTIFS", "VBA", or
"macro" as a description of the spreadsheet logic unless the deliverable
explicitly requires live formula text, an `.xlsm`, or a preserved VBA project.
For normal `.xlsx` outputs, implement the equivalent logic in Python/openpyxl
and write the computed final values to the requested cells. When the user
provides an existing or broken formula, use it as a semantic specification:
honor its referenced ranges, criteria, and aggregation intent, then write the
resulting values.

## Output Requirements

- Save the result to `OUTPUT_PATH`.
- Do not hardcode row counts or column letters — iterate over actual rows in
  the workbook.
- Preserve sheets and cells not mentioned in the instruction.
- When the instruction names a destination range or columns, write derived
  results directly there. Do not insert rows/columns, relocate the source
  table, or sort/delete source records unless that structural change is
  explicitly requested.

## Matching and Target Range Hygiene

- Choose the comparison operator from the instruction and examples: use
  `startswith` for "begins with", substring search for
  "contains/search/occurrence", and exact normalized equality only when a
  whole-cell match is implied. Create small helper functions for comparisons
  and numeric parsing.
- Normalize text by trimming, collapsing repeated spaces/NBSPs, and
  casefolding; when names or labels have punctuation/spacing inconsistencies,
  consider punctuation-insensitive keys. Parse numeric text after removing
  commas/currency symbols while preserving signs and decimal points; handle
  placeholders such as `"-"`, `"$"`, `"$0"`, blanks, and numeric zero
  deliberately. Normalize date keys across `datetime`/`date` objects, Excel
  serials, and date-like strings, and compare at the granularity implied by
  the task; for monthly or period summary grids, canonicalize period labels
  from all sources (sheet names, headers, text months, date cells) and match
  by normalized period plus stated criteria. For date ranges, infer endpoint
  inclusivity from wording and examples.
- Parse `datetime`, `time`, and time-like strings into real Python
  `time`/`datetime` values; write real time values with an Excel
  `number_format` such as `hh:mm:ss AM/PM`, not text substrings.
- For joins, deduplication, grouping, interval lookups, and ordered outputs,
  build explicit normalized keys (composite keys when the task refers to
  multiple fields); preserve original source order within each group unless
  sorting is explicitly requested. Make a first pass to build normalized
  dictionaries/groups/range structures, then a second pass to write results;
  treat error literals such as `#N/A` as meaningful sentinel values when the
  task refers to them.
- For lookups, filters, and label/header matching, treat numeric-looking IDs
  consistently (`330`, `330.0`, and `"330"` are one key). Keep numeric outputs
  numeric; use `number_format` for display formatting instead of converting
  numbers to strings unless text is explicitly required.
- When replacing a generated output area, clear only the instructed target
  range so stale values/formulas do not remain. Preserve formatting, column
  widths, borders, and unrelated cells unless the instruction asks to change
  them. If formatting changes are requested, apply them exactly after writing
  values and only to the requested cells; convert hex colors to ARGB
  (`#FFC000` → `FFFFC000`); for "format as text", set `number_format = '@'`
  and write string values.
- For filtered lists, summaries, and aggregations, collect all source results
  in memory first, preserving the required order, then write from the first
  output row and clear leftover cells below the new results. When adding rows,
  copy style/alignment/number format from an existing template row; when
  deleting rows, delete from bottom to top to avoid row-index shifts.
- Preserve intended blanks as empty cells (`None`) rather than placeholder
  text or `0` unless the task specifies otherwise. For numeric aggregation,
  crosstab, SUMIFS-like, and INDEX/MATCH-style summary outputs, infer
  missing-match behavior from table semantics and examples: numeric summary
  grids usually require literal `0` for no matching records, while filtered
  lists usually require blanks. For blank-sensitive logic, evaluate the
  driving input with `data_only=True` and write `None` for truly blank
  outputs rather than relying on a new formula returning `""`.

## Special Rows and Multi-Step Tasks

- When a target range includes special rows such as `Total`, `Grand Total`,
  `min`, `max`, constraints, headers, or blank separators, do not apply
  ordinary row logic blindly: compute totals as aggregates when indicated, and
  leave constraint/header/blank cells untouched unless explicitly requested.
- For INDEX/MATCH problems where the first row works but subsequent rows fail,
  treat row labels, column/year headers, and criteria labels as a multi-key
  lookup; fill the whole result matrix from the source data table, using
  cached `data_only` values when source cells are formulas.
- For multi-step macro/VBA-style requests, implement every stated operation,
  not just the first deletion/filtering step; re-read the numbered requirements
  before saving and verify later computed columns, totals, and derived fields.
- For residual-balancing tasks, identify data rows separately from min/max
  constraint rows; add positive residuals from unit 1 toward unit 5 without
  exceeding max values; subtract negative residuals from unit 5 toward unit 1
  without going below min values.
- For "every nth row" or OFFSET-style tasks, infer the source column, first
  source row, and step from the provided examples or formulas, then copy the
  actual source values into the requested output range as literals.

Prefer simple, auditable row/column loops over complex workbook XML parsing.
Always execute the final `solution.py` and verify representative target cells
were actually written.

<!-- SLOW_UPDATE_START -->
When the task asks for a formula, macro, VBA code, or a fix to an Excel
formula, still deliver the completed workbook state: compute the intended
results in Python and write literal final values into the requested cells. Do
not write formula strings unless the task explicitly says the output must
contain live formulas. After writing, reload the saved workbook and verify
that every requested target cell contains a non-formula literal where a value
is expected.

Use existing formulas in the workbook as examples/specifications, not as
output. If a cell contains a reference formula such as `=A25` or an
INDEX/MATCH/SUMIFS pattern, parse what source cells/ranges/criteria it refers
to, compute those results, and overwrite the destination with the referenced
or calculated value. For blank-sensitive formula tasks, compute the branch
explicitly: if the driving source cell is truly blank, write `None`;
otherwise write the actual result. Never rely on `IF(...,"",...)` formulas to
be recalculated later.

For lookup/category tasks, locate both the input rows and the lookup table by
headers and nearby labels; support exact keys, numeric-looking keys, and
interval/range tables; then fill every destination row that has a driving
input, not just the first visible example. For schedule/calendar fill tasks,
build a cycle-day-to-periods mapping from the template area first, then fill
the daily rows across all requested class columns; preserve repeated/double
periods exactly as shown by the template.

Keep scripts simple enough to run cleanly. Avoid unnecessary dynamic code
generation and fragile f-strings with regex expressions inside them. If
workbook cells contain arbitrary sample text that could be sensitive, do not
quote large raw cell contents in your response; process them locally in Python
with neutral variable names.
<!-- SLOW_UPDATE_END -->

## Execution Checklist

- Instruction read twice; numbered requirements enumerated and re-checked
  after saving.
- Example output area inspected; its format, precision, and empty-bucket
  behavior matched.
- Header map built from actual cells; sources and destinations
  distinguished by labels and requested range.
- Formula inputs read from the `data_only` view; outputs written as
  computed literals.
- Only the instructed target range cleared and rewritten; unrelated sheets,
  cells, and styles preserved.
- Saved workbook reloaded; representative target cells verified as
  non-formula literals; no stale rows below shorter results.

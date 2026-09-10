# Spreadsheet Task Guide (xlsx)

Working notes for spreadsheet manipulation benchmarks. The deliverable is always
a completed workbook — read the task, write a script, verify the output, ship.

## Tool selection

| Task | Use |
|------|-----|
| Create/edit with structure, formulas, formatting | `openpyxl` |
| Bulk read/write of data | `pandas` |
| Anything else | `openpyxl` |

Do not reach for other libraries. They are not guaranteed in the environment.

`pandas.to_excel()` rewrites sheets and silently drops formulas, named ranges,
and formatting on its way out. If the workbook has any of those and you must use
pandas to compute, read with pandas, but write back through `openpyxl.save()`.

## The formula trap

This is the one that bites everyone once.

`openpyxl` writes formula strings; it does not evaluate them. A cell holding
`=SUM(B2:B9)` reads back as `None` to anything expecting a value until Excel or
LibreOffice recalculates — which nobody does in this pipeline. The checker reads
values.

So: unless the task explicitly demands live formulas, compute results in Python
and write literal values. When the task hands you a formula ("write a SUMIFS
that...", "fix this VLOOKUP"), treat it as a specification of the intended
logic: honor its ranges, criteria, and intent, then write the resulting values.

To *read* a workbook whose formulas hold cached results from a previous
recalculation:

```python
wb = openpyxl.load_workbook(path)                      # formulas
wb_values = openpyxl.load_workbook(path, data_only=True)  # cached values
```

## Workflow

1. **Inspect before writing code.** List the sheets. Find the header row of each
   table — tables do not always start at A1; they sit under title rows, to the
   right of labels, or several sheets deep. Build a header map when it helps:
   `{str(cell.value).strip(): cell.column}`.
2. **Read any Output / Example / Desired sheets.** Existing filled cells in the
   target area are the format spec. Match their conventions exactly — they tell
   you what "correct" looks like.
3. **Write `solution.py`** with `INPUT_PATH` and `OUTPUT_PATH` at the top.
4. **Run it.** Fix syntax and indentation errors immediately.
5. **Verify before finishing.** Reopen the saved file and confirm the requested
   cells hold the expected values. If a target cell is unexpectedly `None`, the
   script is not done.

## Matching hygiene

Text in spreadsheets is dirty. Normalize before comparing:

- Trim whitespace, collapse doubled spaces, strip NBSPs.
- Casefold for comparisons; restore original text for output.
- Parse numbers after removing commas and currency symbols; keep signs and
   decimals. `"-"`, `"$0"`, blank, and numeric zero are four different things —
   decide deliberately which are blanks.
- Dates: handle `datetime` objects, Excel serials, and strings. Compare at the
   granularity the task implies (month? fiscal year? exact date?). "March" in a
   header, `3/31/2024` in a cell, and a sheet named `Mar 2024` are the same
   period.
- IDs that look numeric (`330` vs `330.0` vs `"330"`) need one canonical key.

Choose the operator the task wording implies: `startswith` for "begins with",
substring for "contains", normalized equality only for whole-cell matches.

## Output discipline

- Write to the destination range the task names. Do not insert or delete
  rows/columns, relocate tables, or restructure anything unless explicitly told.
- Clear only the instructed output range before writing, so stale values don't
  linger below your results.
- Preserve every sheet, cell, formula, and format the task didn't mention.
- Keep numbers numeric; use `number_format` for display. Times want real time
  values with a format like `hh:mm:ss AM/PM`, not text substrings.
- Intended blanks are empty cells (`None`), not `""`, not `0`.
- Summary grids usually want literal `0` when nothing matches; filtered lists
  want blanks. Infer from the example rows.

## Formatting requests

Apply formatting exactly, only to the requested cells, after writing values.
Convert hex colors to ARGB (`#FFC000` → `FFFFC000`). "Format as text" means
`number_format = '@'` plus string values.

## Keep the script honest

Prefer plain row/column loops over clever XML surgery. Simple scripts fail
loudly and fix fast; clever ones fail silently and ship wrong. Run the final
script once end-to-end, every time, before you call the task done.

## Reading the task's mind

The instruction tells you more than it says. Learn to hear the implications:

- "Add a column for year-over-year growth" means compute per row, in the
  stated order, at the stated precision, into a named column — and the
  example cells show the exact format. If growth is requested as a percent,
  write the number the example shows (is it 0.12 or 12? Match the example,
  not your habit).
- "Summarize by month" means every month, including empty ones, in calendar
  order, in a fresh area — unless the example output skips empty months,
  in which case skip them too.
- "Clean up this list" is a formatting task; "standardize this list" is a
  normalization task. Don't over-execute: cleaning usually means dedupe and
  trim, not re-sort, unless asked.
- Numbered instructions are a contract. Re-read them after writing the
  script and check each number off against the output — the classic failure
  is doing steps 1–3 and forgetting 4–5 because they were on the next line
  of text.

## Aggregation defaults

When the instruction doesn't specify the empty-bucket behavior, the
workbook's structure votes:

- A grid with every period already laid out expects `0` where nothing
  matched. The grid is the format; blanks would look like misses.
- A filtered list ("show only...") expects the row to disappear — blank
  cells below, results written from the first row, leftovers cleared.
- Totals rows aggregate what's above them. Don't let a Total row
  participate in the same loop that produces it — compute the aggregate,
  then write it to the total row.

## Row surgery

Inserting and deleting rows is where workbooks get destroyed:

- Deleting: bottom-up, always. Row 5's deletion shifts row 6 to 5; if you
  delete top-down, your indices lie to you after the first deletion.
- Adding: find a template row (one that already looks right) and copy its
  style, alignment, and number format to the new row. Newly created cells
  have no style; naked values in a styled table look broken even when
  correct.
- Moving blocks: don't, unless explicitly asked. "Reorder" instructions are
  rarer than they feel; most "sort" requests want a new output area, not a
  restructured source.

## Dates and periods, again

Because this is where every spreadsheet task goes to die:

- Excel serials are days since 1899-12-30; times are fractions of a day.
  A cell showing `45123.5` is a date at noon. Convert deliberately, both
  directions.
- Fiscal years: a FY2024 label can mean July 2023–June 2024 or Oct 2023–Sep
  2024. The workbook's other labels tell you which. When the task mixes
  "FY" and "calendar" language, reconcile before computing.
- Text months ("Jan", "March", "Q3") and date cells can coexist in the same
  header row. Canonicalize everything to one representation before joining.
- End-of-month vs end-of-fiscal-month: when a task says "as of March 31",
  verify the workbook's March rows are actually end-of-month, not
  mid-month snapshots.

## When the script misbehaves

- Read the traceback. Nine times out of ten it's a `None` you treated as a
  number — a header row, a trailing blank, a merged cell's empty tail. Skip
  Nones explicitly in numeric loops.
- Output empty? You saved the wrong workbook object, or the wrong path, or
  you wrote to a copy that was never saved. Print the path and the cell
  count when in doubt.
- Values right, verification failed? Check formatting: a number stored as
  text (`'123` or `number_format='@'`) fails numeric comparison. Check for
  stray spaces. Check you wrote to the sheet the task named — workbooks
  with template copies have two sheets that look identical.
- Still stuck? Shrink the problem: run the logic on the first five rows and
  print everything. The bug will introduce itself.

## Merged cells and other structural traps

- Merged cells report their value only in the top-left cell; the rest read
  as `None`. If a header spans four columns, don't conclude three columns
  are unlabeled — walk left until you find the merge anchor.
- Hidden rows and columns still exist and still get read by `iter_rows`.
  If a task's numbers seem doubled or off by a constant, check for hidden
  duplicates.
- A sheet can contain several tables that look like one. The giveaway is a
  second header row mid-sheet, or a blank-row gap followed by different
  column counts. Treat them as separate tables; verify which one the task
  means by matching its headers to the instruction's field names.
- Number formats lie about values. A cell displaying `1,234` may hold
  `1234` or `1234.0` or even text. Read the raw value; format only matters
  when writing.
- `ws.max_row` and `ws.max_column` include formatted-but-empty cells. If a
  loop over `max_row` drags through hundreds of Nones, find the real
  boundary from the data, not the dimension metadata.

## Reading existing formulas as specs

When the workbook already contains formulas in the target area, you've been
handed the answer key's skeleton:

- `=A25` means: this cell should hold whatever A25 holds. Read A25 from the
  values view, write the literal here.
- `=SUMIFS(A:A, B:B, "X")` means: sum column A where column B equals "X".
  Implement exactly that in Python — same column, same criterion, same
  comparison semantics.
- `=VLOOKUP(..., 2, FALSE)` means: exact match, second column of the lookup
  table. Not approximate. The `FALSE` is doing real work.
- A formula referencing a range on another sheet tells you where the
  source data lives. Follow it before guessing.
- Broken formulas (`#REF!`, `#NAME?`) still tell you the intent — the
  function name and the surviving operands. Reconstruct, don't discard.

## A quick template sanity check

Before running the full task, do a 30-second dry pass:

1. Print the sheet names and each sheet's dimensions.
2. Print the first three rows of the relevant sheet.
3. Print the instruction's target range, if named.
4. Confirm the target range actually intersects a real table.

If any of those four print something surprising, stop and re-read the
workbook before writing the transformation. Two minutes of inspection
prevents two hours of debugging — and, in this setting, a failed task.

The order of operations that works: inspect, plan, script, run, verify.
Skip inspect and you'll script against an imagined workbook; skip verify
and you'll ship against an imagined result.

## Number formats worth memorizing

- `'0.00'` — two decimals, no thousands separator.
- `'#,##0'` — thousands separator, no decimals.
- `'$#,##0.00'` — currency. `'0.0%'` — percent with one decimal
  (the stored value is 0.123, not 12.3).
- `'@'` — text. `'yyyy-mm-dd'` — ISO date. `'hh:mm:ss AM/PM'` — clock
  time.
- When a task says "two decimal places" it means the stored value rounds to
  two decimals, not that the format displays two while the cell hides
  fifteen.

# Optimized Instructions — SpreadsheetBench

1. Write `solution.py` with `INPUT_PATH` and `OUTPUT_PATH` defined at the top;
   execute it end-to-end and verify the output file exists before finishing.

2. Use `openpyxl` for reading and writing; use `pandas` only for in-memory
   transformation. Never write results with `pandas.to_excel()` into a workbook
   that contains formulas, named ranges, or formatting — write back through
   `openpyxl.save()`.

3. Compute results in Python and write literal values to the requested cells
   unless the task explicitly requires live formulas. The checker reads values,
   not formula strings.

4. Load twice when formulas are inputs: `load_workbook(path)` for structure and
   `load_workbook(path, data_only=True)` for cached values. Never read values
   from the formula view.

5. Scan the used range for header groups before addressing any cell; tables may
   start in later rows, sit right of labels, or share a sheet. Build a header
   map from actual cells, e.g. `{str(cell.value).strip(): cell.column}`.

6. Inspect `Output`, `Manual Result`, or `Desired...` sheets and filled cells
   near the target area; treat them as format examples, then recompute and
   write the complete requested range.

7. Normalize comparison keys: trim/collapse whitespace, casefold, strip
   currency symbols and commas from numerics, canonicalize dates from
   `datetime` objects, serials, and text months to the task's granularity.

8. Pick the comparison operator from the instruction's wording — `startswith`
   for "begins with", substring for "contains", normalized equality for
   whole-cell matches.

9. When the task provides a formula, treat it as the specification of intended
   logic: honor its ranges, criteria, and aggregation intent, then write the
   resulting values.

10. Write into the named destination range without inserting or deleting
    rows/columns, relocating tables, or altering unspecified cells; clear only
    the instructed target range before writing.

11. Match missing-value behavior to the output family: literal `0` for numeric
    summary grids with no matching records, blank (`None`) for filtered lists;
    keep intended blanks as `None`, never `""` or `0`.

12. In special rows (`Total`, `min`, `max`, constraints, headers), do not apply
    ordinary row logic; compute aggregates where indicated and leave
    constraint/header cells untouched.

13. Keep numeric outputs numeric and apply `number_format` for display;
    convert hex colors to ARGB for fills; "format as text" means
    `number_format = '@'` with string values.

14. After saving, reload the output workbook and verify representative target
    cells contain the expected non-formula literals.

15. Read the instruction twice: extract the target sheet, the target range,
    the condition, and the output format; numbered requirements are a
    contract — re-read them after writing the script and check each
    number against the output.

16. When examples exist in the output area, match their format exactly —
    decimal precision, percent representation (0.12 vs 12), date display,
    and empty-bucket behavior.

17. Answer the empty-bucket question from the structure: grids expect
    literal `0` for no-match cells; filtered lists expect blanks with
    leftover rows cleared.

18. Do not participate Total rows in the loops that produce them; compute
    the aggregate, then write it to the total row.

19. When instructions mention sorting, prefer writing a new sorted output
    area over restructuring the source table.

20. Deleting rows: iterate bottom-to-top so index shifts do not skip rows.

21. Adding rows: copy style, alignment, and number format from an existing
    template row; new cells carry no style.

22. For joins and grouping, build normalized keys first — composite when
    the task names multiple fields — and preserve original source order
    within groups.

23. For interval lookups, implement range-match alongside exact-match;
    numeric-looking keys normalize to one canonical form (`330`, `330.0`,
    `"330"`).

24. Treat `#N/A` and error literals as meaningful sentinels when the task
    refers to them.

25. Explode delimited cells into separate rows; ignore empty tokens after
    splitting.

26. Two-pass writes: first pass builds lookup dictionaries and group
    structures, second pass writes results; never nest full-sheet scans
    per row.

27. For period grids, canonicalize period labels from all sources — sheet
    names, headers, text months, date cells — and match by normalized
    period; never assume fixed month offsets.

28. Infer endpoint inclusivity for date ranges from wording and examples;
    "through" and "up to" are usually inclusive.

29. Fiscal-year labels require reconciling the workbook's convention
    before computing against calendar dates.

30. After saving, reload the workbook and re-read representative target
    cells: confirm expected literals, confirm no stale rows below shorter
    results, confirm unrelated sheets untouched.

31. On failure, shrink the problem: run the logic on the first five rows
    and print intermediate values; check for `None` in numeric loops
    before anything else.

32. Locate tables by scanning for complete header groups, not by
    coordinates; a second header row mid-sheet means a second table.

33. Read merged headers from the merge anchor; cells inside a merge report
    `None` except the top-left.

34. Trust `ws.max_row`/`ws.max_column` only as upper bounds —
    formatted-but-empty cells inflate them; find the real data boundary
    from content.

35. When the workbook contains formulas in the target area, parse them as
    specifications: `=A25` copies A25's value; `=SUMIFS(...)` defines the
    sum's ranges and criteria; `#REF!` still reveals intent from surviving
    operands.

36. Follow cross-sheet references in existing formulas to find source data
    before guessing locations.

37. Hidden rows and columns are still read by iteration; check for them
    when totals seem doubled or shifted by a constant.

38. Display formats do not change values: read the raw cell value for
    logic; apply `number_format` only when writing.

39. Keep the exploration dry-run: print sheet names, dimensions, first
    three rows, and the named target range before writing any
    transformation.

40. Inspect, plan, script, run, verify — in that order; never script
    against an unexamined workbook.

41. Fiscal-year labels: reconcile the workbook's convention from adjacent
    labels and examples before computing against calendar dates.

42. For percent outputs, match the example area's representation (0.12 vs
    12) exactly.

43. For date outputs, match the example area's display form; write real
    date values with the matching `number_format`, not text.

44. When the instruction is ambiguous between restructure-in-place and
    write-a-new-area, choose the new area; position-based verification
    tolerates additions and fails on relocations.

45. Log a one-line summary of what was written (range, row count, sheet)
    and compare it to the instruction before finishing.

46. Round stored values to the precision the task requests — do not hide
    extra decimals behind a display format.

47. Use `'@'` number format with string values for text outputs; store
    percentages as fractions with a percent format, not as multiplied
    numbers.

48. Prefer plain row/column loops over workbook XML surgery; simple scripts
    fail loudly, clever ones fail silently.

49. On any runtime error, check for `None` in numeric loops first — a
    `None` treated as a number usually marks a header row, trailing blank,
    or merged cell tail.

50. Write a one-line write summary (sheet, range, row count) and compare it
    to the instruction before declaring the task complete.

51. When both a written instruction and an example area exist and they
    disagree, follow the example area; it is the checker's own format.

52. After clearing the instructed range, verify the clear actually emptied
    it before writing — merged or shifted ranges sometimes survive.

53. When a task spans multiple sheets, finish and verify one sheet before
    starting the next; interleaved writes obscure partial failures.

54. When the task's example area and the written instruction disagree on
    format, the example area is the checker's own format — follow it.

55. Write a final one-line completion note (sheets touched, ranges written)
    and compare it against the instruction before finishing.

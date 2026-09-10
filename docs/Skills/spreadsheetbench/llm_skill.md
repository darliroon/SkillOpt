# Comprehensive Guide to Excel Spreadsheet Tasks

## Overview
This guide covers how to complete spreadsheet manipulation tasks using Python.
You will receive an input workbook, an instruction describing the desired
changes, and an output path where the completed workbook must be saved.

## Recommended Libraries

- **openpyxl**: the standard library for reading and writing `.xlsx` files.
  Use it to load workbooks, iterate over cells, modify values, apply formatting,
  and save results.
- **pandas**: useful for data analysis and transformation. You can load sheets
  into DataFrames, compute aggregations, and export results.

Both libraries are widely used and well documented. Choose the one that fits
the task: openpyxl for cell-level control, pandas for data-level operations.

## Step-by-Step Workflow

1. **Read the instruction carefully.** Understand exactly what transformation
   is requested: which sheet, which cells, what condition, and what output.
2. **Load the workbook** with `openpyxl.load_workbook(path)` and inspect the
   sheet names and dimensions.
3. **Explore the data.** Print the first few rows of the relevant sheet to
   understand the structure: headers, data types, and any patterns.
4. **Write your solution script.** Define `INPUT_PATH` and `OUTPUT_PATH`
   variables at the top, then implement the required transformation.
5. **Run the script** and check that the output file is created.
6. **Verify the output.** Reload the saved workbook and confirm the requested
   cells contain the correct values.

## General Best Practices

- **Never hardcode values you should compute.** Read actual cell values and
  compute results programmatically. Hardcoding breaks if the data changes.
- **Iterate, don't assume.** Do not assume the data starts at a fixed position.
  Scan for headers and find the actual boundaries of the data region.
- **Handle edge cases.** Empty cells, missing values, and unusual formats are
  common. Write defensive code that handles them gracefully.
- **Preserve the original data.** Only modify what the instruction asks you to
  modify. Keep other sheets and cells intact.
- **Use appropriate data types.** Write numbers as numbers and text as text.
  Apply number formats when specific display formats are requested.
- **Write clean, readable code.** Use meaningful variable names and add
  comments explaining the logic. This makes errors easier to find.

## Common Pitfalls

- **Overwriting the wrong cells.** Always double-check row and column indices
  before writing. Off-by-one errors are the most common bug.
- **Forgetting to save.** After all modifications, call `wb.save(OUTPUT_PATH)`.
  Without it, no output file is produced.
- **Mixing up rows and columns.** Remember that openpyxl uses `ws[row, column]`
  or `ws.cell(row=..., column=...)` with 1-based indexing.
- **Ignoring formatting requirements.** If the instruction mentions fonts,
  colors, fills, or number formats, use openpyxl's styling features
  (`Font`, `PatternFill`, `Alignment`, `Border`) to apply them.
- **Not testing the script.** Always run the script and inspect the output
  before considering the task complete.

## Useful Patterns

**Finding headers:**
```python
for row in ws.iter_rows(min_row=1, max_row=10):
    for cell in row:
        if cell.value is not None:
            print(cell.coordinate, repr(cell.value))
```

**Filtering rows:**
```python
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] is not None and meets_condition(row):
        results.append(row)
```

**Writing results:**
```python
for i, value in enumerate(results, start=2):
    ws.cell(row=i, column=3, value=value)
wb.save(OUTPUT_PATH)
```

## Final Checklist

- Does the output file exist at `OUTPUT_PATH`?
- Are the requested cells updated with correct values?
- Is the rest of the workbook unchanged?
- Are formatting requirements satisfied?

Complete all checks before submitting the task.

## Working with Formulas

- Use openpyxl to read formula strings from cells (the cell value will
  start with `=` if it contains a formula).
- To write a formula, simply assign the formula string to the cell:
  `ws["B10"] = "=SUM(B2:B9)"`.
- To evaluate formulas, you would need Excel or a library that supports
  calculation; openpyxl does not calculate formulas automatically.
- If your task requires computed values, perform the calculations in Python
  and write the results to the cells.

## Data Cleaning Techniques

- **Removing duplicates**: iterate over rows, keep track of seen values
  with a set, and skip rows that were already processed.
- **Trimming whitespace**: use `str.strip()` on text values before writing
  or comparing.
- **Standardizing case**: use `.lower()` or `.upper()` for comparisons, but
  preserve the original case in output.
- **Handling missing values**: decide whether missing values should become
  empty cells, zeros, or placeholders, and apply that choice consistently.

## Error Handling

- Wrap file operations in try/except blocks to catch missing files or
  permission errors.
- Validate that the expected sheet exists before accessing it:
  `if "Sheet1" in wb.sheetnames: ...`
- Check for `None` values before performing arithmetic on cells.
- Print informative messages when something goes wrong so you can debug
  quickly.

## Performance Tips

- For large files, read with `read_only=True` mode when you only need to
  scan values.
- Minimize the number of save operations — save once at the end.
- Avoid iterating over entire sheets when you know the target range.

## Working with Multiple Sheets

- List all sheets with `wb.sheetnames`.
- Access a specific sheet with `wb["SheetName"]` or `wb.active` for the
  first sheet.
- Copy data between sheets by reading from one and writing to another.
- Create new sheets with `wb.create_sheet("NewSheet")` when the task asks
  for output on a separate sheet.

Remember: read the instruction, inspect the data, write clean code, verify
the output. That is the entire job.

## Working with Headers

- Identify the header row before processing data rows; it is usually the
  first non-empty row, but not always.
- Use headers to locate columns by name instead of hardcoding letters.
- Watch for multi-row headers where a title spans the columns above the
  actual field names.

## Review Before Finishing

- Confirm the output workbook exists and opens cleanly.
- Spot-check several modified cells against the instruction.
- Make sure no unrelated data was changed.

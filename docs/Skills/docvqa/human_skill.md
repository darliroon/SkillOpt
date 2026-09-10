# DocVQA Review Notes

For answering questions against scanned documents — forms, reports, tables,
handwritten lists. The document is the only truth; your job is disciplined
extraction.

## Ground rules

1. Find the answer on the page before answering. Never answer from what the
   document "probably" says. If a question names a field, a row, or a page
   element, go to it first, then read.
2. Answer with the smallest exact span that responds to the question. If it
   asks for a date, give the date — not the sentence containing it.
3. Copy, don't retype. The difference between `10 mg` and `10mg`, `J. Smith`
   and `J Smith`, matters. Preserve capitalization, punctuation, and spacing
   as printed.

## Working tables

- Find the row (or column) the question names, then follow it to the
  requested column (or row). Read the cell at the intersection — not the
  nearest number. Check the header you crossed to confirm it matches what the
  question asked for (year, category, unit).
- Nested or multi-level headers: resolve which sub-header owns your column
  before extracting.
- Comparison questions ("which is higher") — pull both cells first, then
  compare. Don't judge from a glance.

## Forms and labeled fields

- Locate the exact label the question mentions, then take the value from the
  same line, box, or immediately adjacent field. Printed forms put answers in
  predictable slots: after a colon, in the box to the right, below the label.
- Handwriting: read the anchored region carefully. If the question gives an
  anchor ("next to subtotal"), inspect that specific area, then the
  immediately adjacent text.

## Numbers, dates, units

- Bare counts, page numbers, exhibit numbers: digits only, no labels, no
  units. "How many pages" → `12`, not `12 pages`.
- Quantities where the unit is part of the field: include it (`10 mg`,
  `$4,500` if printed that way).
- Dates in the printed form: `03/15/2021` stays `03/15/2021` — don't convert
  to March 15, 2021.
- Don't convert numerals to words or vice versa, don't add currency symbols
  that aren't printed, don't strip leading zeros.

## Disambiguation

- Similar-looking strings cluster together (`$4,500` / `$45,000`;
  `1O` vs `10`). Choose by the surrounding labels and layout, then re-check
  digit by digit before committing.
- Positional and formatting cues in the question are binding: "top-right",
  "underlined", "second entry" tell you exactly which instance to read.
- Ordinal cues (first, last, second) refer to printed order on the page —
  top-to-bottom, left-to-right — unless the layout clearly reads otherwise.

## Before you answer

Verify the span one more time against the page. Then output only the answer
— no explanation, no units that weren't asked for, no partial matches.

## Charts and figures

- Read the axes before any data point: which series is which, what the
  units are, whether the baseline is zero. A bar chart without a zero
  baseline distorts visual comparison — trust the printed values, not the
  pixel heights.
- Questions about chart extremes (highest/lowest) still need the printed
  labels read off one by one. Don't compare by eyeball.
- Legends sometimes number series (1, 2, 3) with the key in a corner.
  Match the number to the name before answering anything about a series.

## Answering "how many" on documents

- Counting visible items (rows, stamps, signatures, checkboxes marked):
  count in printed order, top to bottom, left to right, and re-count once.
  The document's grouping (sections, columns) is the natural chunking.
- "How many pages" — look for the printed page numbers, not your own page
  count of the scan; exhibits sometimes number separately from the
  document.

## Trust the print, not the world

If the document says a form was issued 02/30/2021, the answer to "what is
the issue date" is `02/30/2021`. Your job is extraction, not correction.
Same for totals that don't add up, names that look misspelled, and
handwriting that contradicts the printed label — report what's printed.

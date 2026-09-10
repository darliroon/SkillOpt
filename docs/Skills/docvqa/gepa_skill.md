# DocVQA Skill (Optimized)

Instructions evolved over optimization rounds for document visual question
answering. Later rules refine earlier ones; where they overlap, the later,
more specific rule governs.

## Visual Evidence Discipline

1. Read the document carefully before answering.
2. Prefer the smallest exact text span that answers the question.
3. First locate the region named or implied by the question — a page corner,
   header or letterhead, table-of-contents entry, agenda item, table row or
   column, chart category, or labeled form field — then extract.
4. When several nearby strings look similar, choose the one whose surrounding
   labels or layout best match the question. Re-read ambiguous digits at the
   source resolution before answering; do not infer a value from a nearby row
   or visually similar entry.

## Structured Layout Lookup

5. For tables, first find the row or entry named in the question, then read
   the value under the requested column, header, date, or category; answer
   with that cell only.
6. For tables, maps, and structured layouts, perform a final coordinate
   check: identify the referenced row, building, label, or marker, trace
   horizontally or vertically to the requested field, and verify the selected
   cell against neighboring values.
7. For forms, receipts, or labeled fields, locate the exact role, party, or
   field label mentioned in the question, then copy the filled-in value from
   the same line, box, block, or immediately adjacent field.
8. For table-of-contents, indexed, numbered, or bulleted lists, match the
   requested title, entry, or point number, then follow the same line or list
   item to the associated value; do not take a nearby value from another
   item.
9. Map every qualifier in the question — point numbers, section codes,
   categories, columns, and named fields — to its matching labeled row,
   entry, cell, or role before extracting the answer. In tables, lists, and
   charts, follow the relevant row and column intersection and align the
   requested label with its associated value or series; for comparison
   questions, compare the relevant values directly and return the matching
   item.
10. Treat positional, typographic, and ordering cues in the question as
    binding evidence: use locations such as top-right or bottom-left,
    formatting such as underlining or bold text, and ordinal cues such as
    first or second to select the intended entry before copying its text.
11. For questions asking for a count, page number, exhibit number, or other
    numeric field, return only the exact number associated with the matched
    label. For names or descriptive entries, retain the complete visible
    phrase for the requested field and omit explanatory lead-ins.

## Exact Answer Discipline

12. Copy names, numbers, and dates exactly from the document whenever
    possible; prefer direct extraction over paraphrase.
13. Preserve the document's exact spelling and punctuation for names and
    quoted phrases; do not substitute similar letters or change
    straight/curly quotes, spacing, or parentheses when the visible text
    provides them.
14. Preserve the document's literal representation. Do not convert numerals
    to words, words to symbols or abbreviations, or alter separators,
    capitalization, spelling, or punctuation unless necessary for
    readability.
15. Preserve meaningful visible formatting in extracted answers, including
    currency symbols, percent signs, units, thousands separators, decimal
    precision, date separators, time markers, phone-number punctuation,
    capitalization, titles, and name punctuation.
16. For numeric answers, do not add currency symbols, measurement units, or
    explanatory wording unless they are part of the requested answer span.
17. Do not add quotation marks, spaces, currency symbols, or other
    punctuation merely to make an answer look polished; preserve them only
    when they are visibly part of the extracted span. For short text
    answers, compare case, apostrophes, quotation marks, and spacing
    directly against the source before finalizing.
18. Match the requested answer granularity: for counts, page numbers, exhibit
    numbers, and other bare numeric fields, return only the corresponding
    number without labels or units; for quantities or measurements, include
    the complete visible value together with its unit when the unit is part
    of the field (for example, `10 mg`); for dates, amounts, names, and other
    fields, return only the corresponding exact span, without labels,
    surrounding prose, quotation marks, parenthetical expansions, or a
    trailing period unless those characters are part of the requested answer
    span.
19. For names and labels, verify every character against the visible source.
    For tables, verify the requested row, column, category, and date before
    extracting the value.

## Anchored Handwriting and Nearby Text

20. For handwritten or list/table questions with an anchor term, first
    locate the anchor, then inspect the immediately adjacent text in the same
    row, column, or nearby margin. If legible, provide the best-supported
    nearby span rather than leaving the answer blank.
21. For questions that identify a row, person, label, or nearby marker, first
    locate that reference and trace the associated value in the same row,
    column, or local region. Ignore plausible-looking values from adjacent
    entries.

## Final Verification

22. Before finalizing, compare the answer against nearby alternatives and
    keep the best-supported exact span.
23. Before answering, remove every word that is not part of the smallest
    exact answer span and compare the remaining text character-for-character
    with the visible document.

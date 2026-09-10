# DocVQA Skill

## Visual Evidence Discipline
- Read the document carefully before answering.
- Prefer the smallest exact text span that answers the question.
- When several nearby strings look similar, choose the one whose surrounding
  labels or layout best match the question.
- First locate the region named or implied by the question — a page corner,
  header or letterhead, table-of-contents entry, agenda item, table row or
  column, chart category, or labeled form field — then extract from it.

## Exact Answer Discipline

- Treat leading articles, explanatory words, and answer wrappers as removable
  unless the question explicitly asks for the full phrase. Do not add
  quotation marks, spaces, currency symbols, or other punctuation merely to
  make an answer look polished; preserve them only when they are visibly part
  of the extracted span. For short text answers, compare case, apostrophes,
  quotation marks, and spacing directly against the source before finalizing.

- Match the requested answer granularity: for counts, page numbers, exhibit
  numbers, and other bare numeric fields, return only the corresponding number
  without labels or units. For quantities or measurements, include the
  complete visible value together with its unit when the unit is part of the
  field (for example, `10 mg`). For dates, amounts, names, and other fields,
  return only the corresponding exact span, without labels, surrounding
  prose, quotation marks, parenthetical expansions, or a trailing period
  unless those characters are part of the requested answer span.
- Preserve the document's literal representation. Do not convert numerals to
  words, words to symbols or abbreviations, or alter separators,
  capitalization, spelling, or punctuation unless necessary for readability.
- For numeric answers, do not add currency symbols, measurement units, or
  explanatory wording unless they are part of the requested answer span.
- For names and labels, verify every character against the visible source. For
  tables, verify the requested row, column, category, and date before
  extracting the value.
- Copy names, numbers, and dates exactly from the document whenever possible.
- Prefer direct extraction over paraphrase.
- Before finalizing, compare the answer against nearby alternatives and keep
  the best-supported exact span.

## Reference-Linked Extraction

- For tables, maps, and structured layouts, perform a final coordinate check:
  identify the referenced row, building, label, or marker, trace horizontally
  or vertically to the requested field, and verify the selected cell against
  neighboring values. Re-read ambiguous digits at the source resolution before
  answering; do not infer a value from a nearby row or visually similar entry.
- For questions that identify a row, person, label, or nearby marker, first
  locate that reference and trace the associated value in the same row,
  column, or local region. Ignore plausible-looking values from adjacent
  entries.
- For comparison questions across entries, extract both referenced cells
  first, then compare them directly and return the matching item.
- Before answering, remove every word that is not part of the smallest exact
  answer span and compare the remaining text character-for-character with the
  visible document.

## Spatial, Field, and Formatting Matching
- Treat positional, typographic, and ordering cues in the question as binding
  evidence: use locations such as top-right or bottom-left, formatting such as
  underlining or bold text, and ordinal cues such as first or second to select
  the intended entry before copying its text.
- Map every qualifier in the question, including point numbers, section codes,
  categories, columns, and named fields, to its matching labeled row, entry,
  cell, or role before extracting the answer. In tables, lists, and charts,
  follow the relevant row and column intersection and align the requested
  label with its associated value or series.
- Preserve meaningful visible formatting in extracted answers, including
  currency symbols, percent signs, units, thousands separators, decimal
  precision, date separators, time markers, phone-number punctuation,
  capitalization, titles, and name punctuation.

## Anchored Handwriting / Nearby Text
- For handwritten or list/table questions with an anchor term, first locate
  the anchor, then inspect the immediately adjacent text in the same row,
  column, or nearby margin. If legible, provide the best-supported nearby span
  rather than leaving the answer blank.

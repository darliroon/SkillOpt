# Trace2Skill: DocVQA Execution Lessons

Lessons distilled from recorded DocVQA execution traces.

## Visual Evidence Lessons

V1. Read the document carefully before answering; locate the region named or
implied by the question — a page corner, header or letterhead,
table-of-contents entry, agenda item, table row or column, chart category, or
labeled form field — before extracting anything.

V2. Prefer the smallest exact text span that answers the question; omit
nearby labels, category names, units, or explanatory words unless the
question explicitly asks for them.

V3. When several nearby strings look similar, choose the one whose surrounding
labels or layout best match the question. Re-read ambiguous digits at the
source resolution; failed traces inferred a value from a nearby row or a
visually similar entry.

V4. Before answering, remove every word that is not part of the smallest
exact answer span and compare the remaining text character-for-character with
the visible document.

## Table and Layout Lessons

T1. For tables, first find the row or entry named in the question, then read
the value under the requested column, header, date, or category; answer with
that cell only. Follow the row/column intersection; do not take a nearby
value from another item.

T2. Perform a final coordinate check for tables, maps, and structured
layouts: identify the referenced row, building, label, or marker, trace
horizontally or vertically to the requested field, and verify the selected
cell against neighboring values.

T3. For table-of-contents, indexed, numbered, or bulleted lists, match the
requested title, entry, or point number, then follow the same line or list
item to the associated value.

T4. For forms, receipts, or labeled fields, locate the exact role, party, or
field label mentioned in the question, then copy the filled-in value from the
same line, box, block, or immediately adjacent field.

T5. Map every qualifier in the question — point numbers, section codes,
categories, columns, named fields — to its matching labeled row, entry, cell,
or role before extracting the answer.

T6. Treat positional, typographic, and ordering cues in the question as
binding evidence: locations such as top-right or bottom-left, formatting such
as underlining or bold text, and ordinal cues such as first or second select
the intended entry before copying its text.

## Exact Form Lessons

E1. Copy names, numbers, and dates exactly from the document whenever
possible; prefer direct extraction over paraphrase.

E2. Preserve the document's literal representation. Do not convert numerals
to words, words to symbols or abbreviations, or alter separators,
capitalization, spelling, or punctuation unless necessary for readability.

E3. Do not substitute similar letters or change straight/curly quotes,
spacing, or parentheses when the visible text provides them.

E4. Preserve meaningful visible formatting in extracted answers, including
currency symbols, percent signs, units, thousands separators, decimal
precision, date separators, time markers, phone-number punctuation,
capitalization, titles, and name punctuation.

## Granularity Lessons

G1. Match the requested answer granularity: for counts, page numbers, exhibit
numbers, and other bare numeric fields, return only the corresponding number
without labels or units.

G2. For quantities or measurements, include the complete visible value
together with its unit when the unit is part of the field (for example,
`10 mg`).

G3. For dates, amounts, names, and other fields, return only the
corresponding exact span, without labels, surrounding prose, quotation marks,
parenthetical expansions, or a trailing period unless those characters are
part of the requested answer span.

G4. For numeric answers, do not add currency symbols, measurement units, or
explanatory wording unless they are part of the requested answer span.

G5. For names and labels, verify every character against the visible source.
For tables, verify the requested row, column, category, and date before
extracting the value.

## Handwriting Lessons

H1. For handwritten or list/table questions with an anchor term, first locate
the anchor, then inspect the immediately adjacent text in the same row,
column, or nearby margin. If legible, provide the best-supported nearby span
rather than leaving the answer blank.

H2. For questions that identify a row, person, label, or nearby marker, first
locate that reference and trace the associated value in the same row, column,
or local region; ignore plausible-looking values from adjacent entries.

## Consolidated Observations

O1. The dominant failure modes in traces: extracting from the wrong row or
cell (T1/T2), over-long answers including labels and prose (G1/G3), and
character-level mismatches from retyping instead of copying (E1/E4).


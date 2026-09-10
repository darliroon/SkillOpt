# Optimized Instructions — DocVQA

1. Locate the document region the question names (table, form field, list
   entry, header) before extracting anything.

2. Answer with the smallest exact span that satisfies the question; omit
   labels, units, and surrounding prose unless explicitly requested.

3. Copy the answer character-for-character from the document —
   capitalization, punctuation, spacing, and separators preserved.

4. For tables, find the named row, follow it to the requested column, and
   answer with that cell only.

5. For forms, match the field label, then read the value on the same line or
   in the adjacent box.

6. Treat positional, formatting, and ordinal cues in the question ("top
   right", "underlined", "second entry") as binding.

7. Return bare numbers without units for counts and page numbers; include
   units only when they are part of the printed field (e.g. `10 mg`).

8. When nearby strings look similar, re-read the digits at the source and
   choose by surrounding labels and layout.

9. Prefer direct extraction over paraphrase; never convert numerals, symbols,
   or date formats.

10. Before submitting, compare the answer against nearby alternatives and
    keep the best-supported exact span.

11. Read chart axes and legends before answering chart questions; match
    numbered series to their names in the legend first.

12. For chart extremes, read the printed labels for every candidate before
    comparing; do not compare by visual height.

13. For "how many" questions on visible items, count in printed order
    (top to bottom, left to right) and re-count once before answering.

14. For "how many pages", use the printed page numbers, not your count of
    scanned pages.

15. Extract what is printed, even when it contradicts real-world facts —
    report the document's text, not a correction of it.

16. For handwritten fields, read the anchored region slowly; if illegible,
    provide the best-supported nearby span rather than leaving the answer
    blank.

17. Match question qualifiers (point numbers, section codes, categories) to
    labeled entries before extraction.

18. For comparison questions, extract both referenced cells first, then
    compare and return the matching item.

19. For form fields, read the value written to the right of, below, or
    after the label's colon — in that order of likelihood.

20. For low-quality scans, compare ambiguous character shapes against
    other instances of the same text on the page.

21. Verify the final span character-by-character against the page one last
    time before submitting.

22. When two adjacent entries look identical, disambiguate by the labels
    above and beside them, not by position alone.

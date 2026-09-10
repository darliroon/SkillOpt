# Optimized Instructions — OfficeQA

1. Search with terms naming the exact entity, period, measure, and table
   concept from the question.

2. Use provided parsed pages as primary evidence; search only for what they
   lack.

3. Align every value by row label and exact column header, never by
   proximity; check footnotes and fiscal-vs-calendar blocks.

4. Extract exact values before arithmetic; track each operand's period,
   unit, and role.

5. Enumerate every requested period in a ledger before computing; verify
   completeness and exclude totals and out-of-range columns.

6. Use the latest revised value for a period unless the question fixes an
   edition.

7. Obey quote conventions: price decimals in 32nds mean `99 + 27/32`.

8. Write the direction ledger for currency conversions and derived
   quantities before computing.

9. Divide by `n` for population standard deviation, `n-1` for sample; do not
   round intermediates.

10. Apply the requested unit conversion and number formatting exactly; return
    only the requested numeric value without unit words.

11. Re-check the final answer against the evidence before submitting.

12. Compute percentage change as (Y − X) / X; answer percentage-point
    questions with the arithmetic difference — read the phrasing before
    dividing.

13. For counting questions ("how many months exceeded Z"), enumerate the
    periods in a ledger and count explicitly; exclude footnote and
    preliminary rows.

14. Pull every item's value before ranking; do not rank from narrative
    recollection.

15. Check both operands' units before computing ratios; mixed scales
    produce thousand-fold errors.

16. "According to the release" pins the answer to the printed vintage of
    that release, not the latest revision.

17. Sanity-check the magnitude of the final answer before formatting.

18. For multi-stage questions, freeze the first-stage key with evidence
    before retrieving the second measure.

19. Keep a provenance note (publication, table, edition) for every operand;
    reconcile overlapping vintages before calculating.

20. Match the question's output template exactly: number of values,
    delimiters, signs, and decimal precision.

21. Include symbols and commas only when the answer format requires them.

22. After computing, re-read the question once to confirm the answer
    responds to what was asked.

23. Identify the question type first — direct lookup, calculation,
    comparison, or counting — and apply the matching final verification:
    lookup re-checks the cell, calculation re-checks the formula,
    comparison re-checks all values, counting re-checks the ledger.

24. Do the unit conversion once in the ledger; the formatting pass only
    rounds and decorates, never re-scales.

25. If the question's phrasing names a unit different from the table's,
    convert in the ledger before formatting.

26. Re-derive the final number from the ledger before formatting; a value
    you cannot trace to a ledger line is a candidate, not an answer.

27. Enumerate expected observation counts for inclusive ranges and verify
    the ledger matches before computing statistics.

28. Keep full precision through intermediates; round exactly once, at the
    end, to the requested precision.

29. For "nearest tenth" or "nearest thousand" requests, apply the rounding
    once to the final value, never to operands.

30. When two tables report the same measure for the same period, prefer the
    later-published one unless the question names an edition.

31. When a question spans two measures, retrieve the first, freeze it as a
    key with its date basis, then retrieve the second for exactly that
    basis.

32. Before formatting, confirm the answer's unit is the unit the question
    requested, not the table's reporting unit.

33. Before submitting, re-read the question's final sentence and confirm
    the answer's unit, rounding, and format match it exactly.

34. If the question requests a list, deliver exactly the requested number
    of values in the requested order and delimiter.

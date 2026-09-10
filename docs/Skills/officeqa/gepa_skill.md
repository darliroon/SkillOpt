# OfficeQA Skill (Optimized)

Instructions evolved over optimization rounds for answering financial and
statistical questions against official publications and time-series tables.
Later rules refine earlier ones; where they overlap, the later, more specific
rule governs.

## Retrieval Rules

1. Start by narrowing to the most likely candidate file before reading long
   passages.
2. Prefer targeted search terms that name the exact entity, period, measure,
   or table concept from the question.
3. When an external official time-series observation is needed, prefer the
   source's series/data-download/table page once identified.
4. If exact-date or guessed-value searches return empty results, stop
   repeating them; broaden to the official series name/code plus `data` or
   `download` and use the table values. (Refinement: repeated identical
   empty-result searches waste the step budget — after two empty results,
   switch strategy rather than re-issuing the same query with minor
   variations.)
5. Treat provided/oracle parsed pages as primary evidence: if they contain
   the relevant table and period, extract directly from them before searching
   elsewhere; search only for missing continuation pages, missing periods, or
   an official actual value not present.
6. After a promising match, read only a small surrounding span and verify it
   matches the requested year, basis, and unit.
7. If the requested date range extends beyond the provided/oracle page, first
   enumerate the required periods and verify that every period is present in
   evidence. Do not compute from a partial ledger or fill missing periods
   from memory; retrieve continuation pages, adjacent issues, or a later
   issue of the same table that contains the missing dates/revisions.
8. When a search term has multiple plausible matches, inspect each match's
   surrounding table title, header hierarchy, date basis, unit, and row
   semantics before selecting evidence; never use the first matching row
   solely because its label matches.
9. Resolve abbreviated or inherited table labels from the full header
   hierarchy before extraction, carrying forward the applicable year, date,
   category, and unit only when the table structure clearly establishes
   them.

## Evidence Rules

10. Extract the exact value from the retrieved text before doing any
    arithmetic.
11. Keep track of each operand's period, unit, and semantic role so nearby
    proxy values are not mixed in.
12. For tables, align values by row label and exact column header, not
    proximity alone; watch for continued or unlabeled columns, footnotes,
    adjacent amount-versus-percent columns, fiscal-year versus calendar-year
    sections, and repeated month rows under different year blocks.
13. When a page contains multiple nearby sections with similar labels, use
    only the section whose title and row label match the requested measure
    exactly; do not compute from the first visible table if the requested
    measure or table title is absent or only partially shown.
14. If the question asks for a transformed or derived quantity, compute only
    after confirming every operand.
15. For Treasury financing narratives, label each amount by transaction role
    before calculating: offered amount, tenders/subscriptions received,
    tenders accepted, competitive/noncompetitive accepted, foreign or
    Government-account exchange tenders, refunding, and new cash are not
    interchangeable.
16. When converting currencies or scales, make a direction ledger first:
    source table unit, source currency, exchange-rate orientation (foreign
    currency per U.S. dollar means divide by the rate; U.S. dollars per
    foreign unit means multiply), and requested final unit.
17. For multi-stage questions where one table determines the period/entity
    used in another lookup, freeze that derived key with evidence first, then
    retrieve the second measure only for that exact month/year/reporting
    date/entity.
18. For inclusive time-series ranges, make a period-by-period ledger covering
    every requested month/year exactly once, preserving calendar versus
    fiscal basis, end-of-month status, source units, and any specified
    adjustments.

## Calculation Rules

19. For derived comparisons, preserve the direction and sign implied by the
    wording: "change from A to B" means B minus A; "former than latter" means
    former minus latter; "share accounted for by X" means X divided by the
    stated total; paired "gap" questions require computing each within-row
    difference before ranking.
20. For statistical, regression, correlation, and growth-rate questions,
    write a formula ledger before calculating: confirm the exact
    series/endpoints, ordered vector, elapsed intervals, and requested
    convention such as continuously compounded rate, CAGR, Pearson
    correlation, or OLS index/year choice.
21. For statistical transforms over time-series windows, confirm endpoint
    inclusion/exclusion exactly as worded, use consecutive time indices for
    trend regressions when appropriate, sort values before medians, and for
    logarithmic growth use ln(final/initial) before converting to the
    requested percentage format.
22. Before computing any statistic, write the intended formula and
    denominator convention. If the prompt explicitly says population
    standard deviation, divide by `n`; if it says sample, divide by `n-1`;
    for a z-score comparing one observation against a small comparison set
    with no population convention stated, estimate dispersion with the sample
    standard deviation of the comparison set.
23. Do not round intermediate operands, weighted averages, logs,
    exchange-rate conversions, or standard deviations before the final
    requested rounding.
24. For long inclusive ranges, first enumerate the expected count of
    observations and the first/last period, then verify the ledger has
    exactly that count. Exclude totals, cumulative-to-date columns,
    comparable-period columns, estimates, and extra latest-month columns
    outside the requested calendar or fiscal range.
25. For Treasury security quotations, obey the table's quote basis. If the
    table states that price decimals are 32nds, convert quotes such as
    `99.27` as `99 + 27/32`, not as decimal `99.27`. If a task asks for
    smoothing, averaging, or forecasting in a target currency using
    period-specific exchange rates, convert each period's observation to the
    target currency first unless the prompt explicitly says to compute in the
    source currency and convert only the final result.

## Answer Rules

26. Before finalizing, enforce the requested unit and format: convert
    thousands/millions/billions or full nominal dollars as needed, then apply
    no-comma, fixed-decimal, whole-number, or nearest-tenth/thousandth
    formatting exactly as asked.
27. Return the final answer only after one last consistency check against
    the retrieved evidence; copy the final answer from a checked value, not
    from an unverified intermediate guess.
28. Match any requested output template exactly. Unless the prompt explicitly
    asks for unit words or explanatory text, return only the numeric value or
    requested list; do not append words such as `million`, `dollars`,
    `percent`, or `percentage points`. Include symbols/commas only when the
    prompt requests currency-formatted output or the answer format clearly
    requires them.

## Late Additions

29. Before computing any percentage change, confirm whether the question
asks for percent change — (Y − X) / X — or percentage points — the
arithmetic difference. The two are visually similar and were conflated in
evaluation; read the phrasing before dividing.

30. For counting questions ("how many months exceeded Z"), enumerate the
periods in a ledger and count explicitly; eyeballed counts missed boundary
months or included footnote rows.

31. For ratio questions, verify both operands share the same table, month,
and unit before dividing; mixed scales (millions vs thousands) produced
thousand-fold errors.

32. "According to the release" phrasing pins the answer to the printed
vintage of that document, not the latest revision on the website.

33. Sanity-check the final answer's magnitude before formatting — an
impossible rate usually means a decimal, unit, or vintage error, and should
trigger re-verification of the ledger rather than submission.

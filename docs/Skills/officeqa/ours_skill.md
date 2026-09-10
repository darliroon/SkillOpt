# OfficeQA Skill

## Retrieval Discipline
- Start by narrowing to the most likely candidate file before reading long
  passages.
- Prefer targeted search terms that name the exact entity, period, measure, or
  table concept from the question.
- When an external official time-series observation is needed, prefer the
  source's series/data-download/table page once identified. If exact-date or
  guessed-value searches return empty results, stop repeating them; broaden to
  the official series name/code plus `data` or `download` and use the table
  values.
- Treat provided/oracle parsed pages as primary evidence: if they contain the
  relevant table and period, extract directly from them before searching
  elsewhere; search only for missing continuation pages, missing periods, or
  an official actual value not present.
- If the requested date range extends beyond the provided page, first
  enumerate the required periods and verify every period is present in
  evidence. Do not compute from a partial ledger or fill missing periods from
  memory; retrieve continuation pages or a later issue containing the missing
  dates/revisions.
- After a promising match, read only a small surrounding span and verify it
  matches the requested year, basis, and unit.
- When a search term has multiple plausible matches, inspect each match's
  table title, header hierarchy, date basis, unit, and row semantics before
  selecting evidence; never use the first matching row solely because its
  label matches.
- Resolve abbreviated or inherited table labels from the full header
  hierarchy before extraction.

## Evidence Discipline
- For tables, charts, and multi-period calculations, map each requested
  concept and operand to its table, row or date, column, period, and unit
  before computing. Verify the complete requested series is present; confirm
  selections against headings, labels, footnotes, and adjacent-period values;
  do not substitute similar nearby rows, cumulative or annual series,
  fiscal-year data, proxy measures, or partial chart observations.
- Align values by row label and exact column header, not proximity; watch for
  continued or unlabeled columns, footnotes, adjacent amount-vs-percent
  columns, fiscal-year versus calendar-year sections, and repeated month rows
  under different year blocks.
- Preserve source conventions during extraction and arithmetic, including
  prices quoted in 32nds (`99.27` = `99 + 27/32`), preliminary values,
  annualized rates, and calendar-versus-fiscal definitions. Convert only after
  identifying the convention, and apply it consistently to every operand.
- Extract the exact value from the retrieved text before doing any
  arithmetic; keep track of each operand's period, unit, and semantic role so
  nearby proxy values are not mixed in.
- If the question asks for a transformed or derived quantity, compute only
  after confirming every operand.

## Computation Ledger
- When a table reports issue-level or row-level amounts without an explicit
  total, enumerate all rows within the requested table boundaries, exclude
  headers, subtotals, footnote artifacts, and unrelated categories, and sum
  only after confirming the row set is complete and in one unit.
- For multi-operand statistics or aggregations, record a compact ledger of row
  label, selected column, value, unit, and semantic role; verify the operand
  count and coverage before applying the formula.
- Write the formula and denominator convention before computing a statistic:
  population standard deviation divides by `n`, sample by `n-1`; for a
  z-score against a small comparison set with no stated convention, use the
  sample standard deviation of the comparison set. Do not round intermediate
  operands, weighted averages, logs, exchange-rate conversions, or standard
  deviations before the final requested rounding.
- For derived comparisons, preserve direction and sign: "change from A to B"
  means B minus A; "share accounted for by X" means X divided by the stated
  total; paired "gap" questions require each within-row difference computed
  before ranking.
- For a requested peak, minimum, or ranking, retrieve the complete in-range
  comparable series and compare all observations explicitly; never infer an
  extremum from narrative commentary or an incomplete extraction.

## Revision and Series Reconciliation
- When a requested period appears in multiple editions or table variants,
  identify the exact requested table and measure first, then use the latest
  final/revised observation available for that period unless the question
  explicitly fixes an edition. Do not mix an earlier estimate, a later
  revision, and a differently scoped table in one series.
- For each selected value, retain publication/table provenance in the ledger;
  reconcile overlapping values before calculation, selecting one consistent
  basis for all operands.

## Final Answer Discipline
- Enforce the requested unit and format before finalizing: convert
  thousands/millions/billions or full nominal dollars as needed, then apply
  no-comma, fixed-decimal, whole-number, or nearest-tenth/thousandth
  formatting exactly as asked.
- Return the final answer only after one last consistency check against the
  retrieved evidence; copy it from a checked value, not an unverified
  intermediate guess.
- Treat the requested output syntax as a hard constraint: emit only the
  requested payload, using any required wrapper, number of values,
  delimiters, signs, and decimal precision exactly as specified. Do not add
  explanations, currency or percentage symbols, derivations, or surrounding
  prose unless explicitly requested.

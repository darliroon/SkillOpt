# SearchQA Field Guide

Notes from years of running Jeopardy-style trivia QA against web-search evidence.
Read this once, internalize it, then trust it.

## How the evidence behaves

SearchQA questions come with retrieved pages — titles, snippets, and scraped trivia
databases. The answer is almost always in there, but rarely where you first look.

1. Match on the rare words. Proper names, dates, quoted phrases, and unusual terms
   are what tie a question to its page. Two or three distinctive terms appearing in
   the same passage is a far stronger signal than ten generic words scattered across
   different documents.
2. Titles carry weight. If a document title repeats two or three clue terms, the
   answer is probably named in that title or in its snippet. But never answer with
   the title itself unless the question asks for exactly that entity — often the
   title is context and the answer is a *different* typed entity inside the snippet.
3. Snippets from trivia databases have their own layout. You'll see things like
   `HISTORY | clue text | answer`, or `clue. ANSWER:`, or a `right:` field. When the
   question matches the clue part, take the answer field — not the category, not the
   whole sentence.
4. Corroboration beats recency. If three snippets support the same entity and one
   supports a rival, take the entity with three votes unless the lone snippet is the
   only one that actually addresses the question's constraint.

## Getting the answer form right

This is where most points are lost. The question asks for an entity; the grader
wants one specific surface form.

- Answer the headword. "This company", "this river", "this film" — strip the frame.
  Give `Nabisco`, not `the Nabisco Company`. Give `Nike`, not `Nike, Inc.` Legal
  suffixes (Inc., Corp., LLC) go unless the question demands the full legal name.
- Keep geographic designators that are part of the name. It's `Lake Okeechobee`,
  `Tampa Bay`, `Olduvai Gorge` — not `Okeechobee`, `Bay`, `Gorge`. If the question
  asks "this lake", the word Lake is in the question's frame, but the *name* still
  needs it. Judgment call: if removing the designator leaves an ambiguous word
  (there are many Bays), keep it.
- Copy the form the evidence gives. If the strongest snippet says `Muhammad Ali`,
  don't answer `Cassius Clay` because you know the history. Capitalization,
  hyphens, apostrophes — straight quotes, not curly ones — copy them. Trivia
  graders are literal.
- Singular for category answers. When a clue says "these places" or lists examples,
  the expected answer is usually the singular headword of the category: `volcano`,
  not `volcanoes`. Plural only if the term is inherently plural (`Great Lakes`).
- Surnames are usually enough for people — but not always. If the clue says "this
   president", `Lincoln` is fine. If it's a crossword-style clue about a first name,
   give the first name. When unsure, the canonical full name used by the evidence
   is the safe play; a lone ambiguous first name is not.

## Jeopardy conventions

The phrasing of the clue tells you the shape of the answer.

- "This man's third wife was Jiang Qing" — the answer is the *husband* (Mao), not
  Jiang Qing. Watch relation direction everywhere: "A is evidence of this B" wants
  B; "home to these characters" wants the place, not the characters.
- "X, Y, and Z, for short" or a bare comma-separated list — they're asking for the
  class that contains all of them. Answer the parent category, not one of the
  listed examples.
- "Known as", "dubbed", "nicknamed" — answer the nickname itself, not the formal
  name it maps to (or vice versa, read carefully which direction).
- Letter counts in parentheses are hard constraints. `(5)` means five letters.
  Don't return a six-letter synonym.
- Quotes around a word usually signal wordplay, but the answer is still the real
  entity. Solve the pun, then answer with the real thing the evidence supports.
- "Seen here" with a missing image: ignore it. The text clues are sufficient; don't
  stall waiting for a picture.

## Process

1. Read the clue twice. Mark the answer-type noun ("this novel", "she", "these
   mountains") and every hard constraint (dates, superlatives, nationalities).
2. Pull the two or three most distinctive terms and find the pages where they
   co-occur.
3. From the best page, extract the entity that satisfies the type AND all the
   constraints. Reject anything that fails even one constraint.
4. Decide the surface form per the rules above.
5. Output only the answer — no explanation, no hedging, no "the answer is".
   If an answer tag is specified (`<answer>...</answer>`), use it exactly.

If two candidates survive every filter, prefer the one whose evidence repeats more
of the clue's distinctive facts. If still tied, take the one the trivia-database
snippet format actually labels as the answer.

## Dates, numbers, and units

Trivia answers involving time and quantity have their own conventions:

- Decades and centuries: answer in the form the clue uses ("the 1890s", "the
  nineteenth century") — don't switch conventions on your own.
- Ordinals for monarchs and popes stay attached: `Edward VII`, `Pius XII`.
  Dropping the ordinal creates ambiguity and loses the point.
- Currency amounts: give the number as printed in the evidence, including
  commas if the answer field shows them.
- Sports scoring conventions belong to the sport: set scores in tennis,
  innings in cricket, strokes in golf. Don't reformat.
- Titles of works keep their articles when the article is part of the title:
  *The Great Gatsby*, but *Moby-Dick*. Evidence is the tiebreaker.

## When evidence is thin

Sometimes the best page only partially answers the question. In rough order
of preference:

1. A snippet whose clue facts match exactly, with the answer in a labeled
   answer field — take it as-is.
2. A title that names the entity and a snippet confirming the relation —
   take the entity in its title form.
3. Two snippets that each carry half the constraint — combine only if the
   halves are directly compatible (same entity, same event, same date).
4. Nothing solid — then, and only then, answer from your own knowledge, and
   still format it per the surface-form rules above.

Never leave a trivia question blank. A plausible, well-formed guess beats an
empty response; the conventions in this guide exist to make guesses land in
the grader's target form.

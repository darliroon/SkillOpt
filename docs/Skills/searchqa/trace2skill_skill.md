# Trace2Skill: SearchQA Execution Lessons

This guide consolidates lessons distilled from a large set of recorded SearchQA
execution traces, organized by workflow stage and recurring failure pattern.

## Workflow Lessons

W1. Start every question by locating the answer-type noun phrase — "this author",
"these islands", "the currency of" — before touching the evidence. The requested
type is the primary filter for every candidate.

W2. Extract the two or three most distinctive clue terms (proper names, dates,
numbers, quoted strings, unusual words) and match documents where those terms
co-occur. Documents that share only generic vocabulary with the question are
noise.

W3. Read document titles as first-class evidence. When a title repeats several
clue terms, the answer is often the title entity — but verify against the
question's requested type before committing. If the type differs from the title
entity, extract the matching typed entity from the snippet instead.

W4. Trivia-database snippets follow scraped formats such as `CATEGORY | clue |
answer`, `clue. ANSWER: ...`, or labeled fields like `right:`. When the question
text matches the clue portion, answer with the answer field. Traces show many
failures where the whole sentence or the category was returned instead.

W5. Prefer an explicitly stated answer over an inferred one. Outside knowledge
should only break ties, never override the evidence.

## Answer Granularity Lessons

G1. Return the minimal answer span that satisfies the question. Do not append
role titles, product flavor adjectives, or descriptive clauses that the clue
already supplies.

G2. Strip generic descriptors and legal suffixes. "This company" wants `Reebok`,
not `Reebok International Ltd.`; "this band" wants `Nirvana`, not `the American
rock band Nirvana`.

G3. For category questions — "these are all examples of what?" — answer the
singular headword of the shared class (`river`, `novelist`, `currency`), not a
descriptive phrase and not one of the listed examples.

G4. Do not over-shorten. Conventional name components must survive: `Lake
Okeechobee` stays `Lake Okeechobee`, `Olduvai Gorge` stays `Olduvai Gorge`.
Removing a designator that is part of the proper name caused repeated failures
in the traces.

G5. Person answers: use the conventional form the evidence supports. A surname
alone is acceptable when the clue frame expects it; otherwise use the canonical
full name. A bare given name is usually wrong when a full name is available.

G6. Answer the base grammatical form the clue expects. Do not pluralize just
because the clue says "these" or "those" — the trivia answer key usually stores
the singular headword.

## Surface Form Lessons

S1. Copy the answer occurrence literally from the evidence: capitalization,
spacing, hyphens, apostrophes, quotation marks. Use straight apostrophes when
the evidence uses them; do not substitute typographic quotes.

S2. Do not normalize spellings. If the evidence writes `Muammar Gaddafi`, do not
answer `Moammar Kadafi` — even if you believe the second spelling is more
standard.

S3. When several attested variants exist, prefer the form that appears in the
strongest clue-aligned evidence — usually the snippet whose other facts also
match the question.

## Failure Patterns

F1. **Relation reversal.** "His third wife was Jiang Qing" asks for the husband.
"A is evidence of this B" asks for B. Many failed traces answered with the
entity named in the clue instead of the relation target. Always parse which side
of the relation the question requests.

F2. **Example-to-class confusion.** When a clue lists examples ("X, Y, and Z
are among these..."), the answer is the encompassing class or parent entity,
never one of the examples. Failed traces repeatedly returned a listed example.

F3. **Frame subtraction errors.** The question's type noun ("this river", "this
company") usually belongs to the question frame, not the answer. Answer `Volga`
for "this river", not `the Volga River` — but keep designators that are part of
the proper name (G4). This is a subtle distinction; when in doubt, prefer the
attested full proper name from the evidence.

F4. **Letter-count violations.** Parenthetical counts `(5)` are hard constraints.
Answers of the wrong length were an avoidable failure class. When a count is
given, verify the candidate's length before submitting.

F5. **Quotation-anchor errors.** When the clue quotes a lyric, slogan, or title
and asks for an associated "this X", the quote is evidence — the answer is the
associated person, work, or entity, not the quote itself. Failed traces returned
the quoted string.

F6. **Missing-image stalls.** Clues referencing "seen here" or "pictured" with
no image available should be answered from text alone. Traces show agents
refusing to answer; the text clues were sufficient.

F7. **Dual-definition clues.** Wording like "X, or what Y does" wants the single
word satisfying both senses. Choose the word that fits both branches, in the
inflected form the clue requires.

## Consolidated Observations

O1. Across traces, the single highest-impact habit is W1 + F1 combined: decide
the answer type and the relation direction before scanning candidates. Most
catastrophic misses came from skipping this step.

O2. The second highest-impact habit is S1: copying the answer's surface form
exactly from clue-aligned evidence. Paraphrase and regularization are the most
common near-miss failure modes.

O3. When two candidates survive all filters, prefer the one whose supporting
snippet repeats more of the clue's distinctive facts; corroboration across
multiple snippets breaks remaining ties.

O4. Output discipline: place only the final answer inside any required answer
tags. No explanations, no hedging, no restatement of the question.

## Evidence Matching Detail Lessons

E1. Start by identifying the most distinctive terms in the question: proper
names, dates, titles, quoted phrases, unusual words, roles, relationships,
and category descriptors.

E2. Prioritize passages or document titles where several distinctive clue
terms occur together, especially when the wording directly repeats or
closely paraphrases the question.

E3. Treat document titles as useful evidence: the answer is often named in
a title while the snippet confirms the clue facts.

E4. Do not assume the document title itself is the answer. If the requested
type differs from the title entity, use the title as context and extract
the matching typed entity from the snippet or clue relationship.

E5. For "known as", "called", "defined as", or category/type clues, choose
the canonical term explicitly used in the strongest matching title/snippet
or scraped answer field rather than inventing a related derivative or
near-synonym from the clue wording. When multiple plausible candidates
appear, prefer the candidate whose evidence directly states the requested
relationship and repeats the most distinctive clue facts.

E6. Ignore noisy results that only match generic words; prefer evidence
that directly connects the clue facts to one specific entity.

E7. Tolerate mechanical noise such as run-together words, OCR errors,
misspellings, omitted punctuation, and missing diacritics when matching
evidence semantically; preserve the selected answer occurrence literally at
output time rather than carrying the clue normalization into the answer.

E8. Validate each candidate against the full intersection of the question's
constraints, rejecting candidates that satisfy only a generic subset. When
no single passage contains the complete answer, combine directly compatible
facts across relevant passages; infer a shared category or property only
when it fits every cited example and constraint.

E9. If multiple snippets support the same entity, use that corroboration to
choose the canonical or common form of the answer.

## Answer-Type Inference Lessons

A1. For Jeopardy-style wording such as "this man", "this group", "this
film", "this country", "this system", "he", or "his wife", infer the
expected answer type before choosing the answer, and use that expected type
to validate candidates.

A2. Treat modifiers attached to the requested type as hard filters, not
background flavor: constraints like dates, "largest", "2-letter-named",
"1978 remake", "hot dog brand", "dual throne", or "on this company's
board" must all fit the candidate before you answer.

A3. For clues centered on creative works — books, films, plays, songs,
poems — first determine whether the clue asks for the work itself, its
creator, a performer or cast member, a character, a quotation source, or a
setting. Verbs such as "wrote", "directed", "stars", "played", and "set
in", plus pronouns like "he" or "her", usually determine the target.

A4. For fill-in-style clues with placeholders such as "this", "these", or
"one of these", substitute each candidate back into the clue and choose the
concise answer that makes the full phrase, title, or fact read correctly.

A5. For terse clues that are just examples or names separated by commas,
slashes, or "or", infer the shared category, class, or synonym that links
them, then answer with that concise common term.

A6. For clues asking for a first name, abbreviation, acronym, or lyric
word, return that exact constrained form rather than the fuller person,
title, or explanation.

## Additional Failure Patterns

F8. **Snippet-format misreads.** Retrieval snippets may contain the clue
and answer in scraped formats such as `CATEGORY | clue | answer`, `clue.
ANSWER`, or labels like `right:`. Extract the answer field, not the
category or the whole clue sentence. (Related to W4; kept separately
because traces failed here even after learning W4 — the category column is
sometimes the more eye-catching text.)

F9. **Wordplay avoidance.** If the clue contains wordplay, quotation marks,
or puns, treat them as hints, but answer with the real entity supported by
the evidence.

F10. **Quote-source confusion.** For song, poem, nursery-rhyme, or
quotation clues, first decide whether the question asks for a missing word
or phrase from the quote or for the associated creator, performer, or work;
use pronouns and answer-type signals to choose the right target.

F11. **Quotation-anchor reuse.** If a clue includes a quoted title, quoted
narration or lyric, named event, slogan, or other distinctive phrase but
asks for an associated "this" entity, treat the quote or name as evidence
to identify the requested person, work, place, group, category, source, or
term; do not return the quoted anchor unless the clue explicitly asks for
it.

F12. **Dual-definition form errors.** In dual-definition clues using
wording like "X, or what Y does", choose the single word that satisfies
both senses and preserve the required inflected form.

F13. **Unavailable-image refusal.** If the clue references an unavailable
image or link with wording like "seen here", "pictured", or parenthetical
visual hints, rely on the textual clues and context to infer the answer.

F14. **Quotation-continuation errors.** If the question gives the start of
a quotation or phrase, answer with the exact missing continuation from the
context, not a paraphrase of the rest.

F15. **Constrained-form expansion.** When a clue asks for a constrained
form, return that exact form; expanding it to the full official name or
translating it loses the point even when the expansion is factually
correct.

## Cross-Reference Notes

N1. O1 generalizes F1–F3: type and relation direction are decided before
candidate scanning, never after.

N2. O2 generalizes S1–S3 and E-entries in the Evidence sections:
surface-form fidelity is clue-specific; reusing a canonical form selected
for another clue about the same entity caused repeated near-misses.

N3. G3 and A5 both address example-list clues from different trace batches;
apply together — answer the shared class headword, never a listed example.

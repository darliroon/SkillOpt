# Optimized Instructions — SearchQA

1. Identify the requested answer type from the question's noun frame ("this
   river", "she", "these nations") before selecting any candidate.

2. Match documents by the co-occurrence of the question's distinctive terms —
   names, dates, numbers, quoted phrases — not by generic vocabulary overlap.

3. Answer with the minimal span that satisfies the question. Omit the question's
   own type noun, role titles, and descriptive modifiers that merely repeat the
   clue.

4. Preserve the answer's attested surface form exactly: capitalization,
   spelling, hyphens, apostrophes, and quotation marks copied from the
   clue-aligned evidence.

5. Strip legal suffixes (Inc., Corp., Ltd.) and generic descriptors from
   organization answers unless the full legal name is explicitly requested.

6. Keep inseparable designators of proper names: "Lake Okeechobee", "Mount
   Whitney", "Tampa Bay".

7. For category clues listing examples, return the shared parent class in its
   singular headword form.

8. Parse relation direction: if the clue names an entity and describes its
   relation to the requested answer ("his wife was X"), answer the relation's
   other endpoint.

9. Treat parenthetical letter counts as hard length constraints.

10. When a trivia snippet formats content as `CATEGORY | clue | answer`, return
    the answer field only.

11. Prefer the candidate supported by the snippet that repeats the most
    distinctive clue facts; use cross-snippet corroboration to break ties.

12. Output only the answer, inside any required answer tags, with no
    explanations or restatements.

13. If the clue says examples, models, breeds, members, or items "include",
    "like", or "such as" named entities, treat those names as evidence for
    the requested parent class; answer the encompassing brand, animal,
    category, place, or term requested by "this", not one of the examples.

14. If the question gives the start of a quotation, answer with the exact
    missing continuation from the context.

15. For song, poem, nursery-rhyme, or quotation clues, decide whether the
    question asks for a missing word from the quote or for the associated
    creator, performer, or work; use pronouns and answer-type signals to
    choose the target.

16. Treat a quoted title, lyric, slogan, or event in the clue as evidence
    for the associated entity; do not return the quoted anchor unless the
    clue explicitly asks for it.

17. Treat wordplay, quotation marks, and puns as hints; answer with the
    real entity the evidence supports.

18. For dual-definition clues ("X, or what Y does"), choose the single word
    satisfying both senses, in the required inflected form.

19. Ignore unavailable images ("seen here", "pictured"); answer from the
    textual clues.

20. Preserve conventional abbreviations and stylized forms attested in the
    evidence, such as "St." in names of saints.

21. Preserve ordinary ASCII punctuation from the evidence, especially
    straight apostrophes; do not substitute typographic quotes.

22. For natural geographic features, keep conventional designators ("Lake",
    "River", "Bay", "Gorge", "Mount", "Island") that are part of the proper
    name or match the requested feature type.

23. For person answers, prefer the conventional supported name; use a
    surname, first name, or regnal name alone only when the clue or source
    clearly expects that short form.

24. Return the grammatical base form expected by the clue; do not add a
    plural "s" merely because the clue uses plural words like "these" or
    "those".

25. For common-noun category answers, default to the singular dictionary
    headword; use a plural only when the term is inherently plural or the
    answer field gives a plural phrase.

26. For fill-in-the-blank or definitional clues using "this" or "that",
    provide a standalone noun phrase with a natural article ("the highest
    point", not "its highest point").

27. For clues about things replaced or substituted, answer the broad
    headword of the thing replaced unless the clue requires a narrowing
    modifier.

28. Infer the answer type from grammatical cues — pronouns,
    demonstratives, number, role nouns, predicates — before scanning
    candidates.

29. Treat modifiers attached to the requested type (dates, "largest",
    "1978 remake", "2-letter-named") as hard filters every candidate must
    satisfy.

30. For creative-work clues, determine the requested target first — the
    work, creator, performer, character, quotation source, or setting —
    using verbs ("wrote", "directed", "stars", "set in") and pronouns.

31. For terse example-list clues, infer the shared category linking the
    examples and answer with that concise common term.

32. For dictionary-style definitions, return the lexical headword or
    category label alone, without contextual modifiers such as purpose,
    era, or subtype.

33. For fragment clues (a bare quotation, title, list, or label), infer the
    unstated relation from the closest matching passages and return the
    relation's object, not a restatement of the fragment.

34. Tolerate OCR noise and missing punctuation when matching evidence
    semantically, but copy the answer occurrence literally.

35. When no single passage contains the complete answer, combine directly
    compatible facts across passages; infer a shared category only when it
    fits every cited example and constraint.

36. For declarative quiz wording ("this company", "these mountains"),
    treat the type noun as question frame, not response content; return the
    proper name or identifying term alone.

37. For bare pairs or lists of proper names, check whether the context
    repeatedly associates each name with the same place, institution, or
    title; return the semantic value of that shared qualifier.

38. For an isolated quotation or catchphrase, distinguish its documented
    source from a person popularly associated with it; return the source
    the passages explicitly attach it to.

39. When equivalent surface variants exist, prefer the clue-aligned form at
    the requested granularity over a canonical form chosen for a different
    clue about the same entity.

40. Before submitting, perform a slot check: mark which words belong inside
    the answer slot and copy only the contiguous clue-aligned occurrence
    that fills it.

41. Do not add honorifics, middle initials, or expanded formal names when
    the evidence supports a shorter conventional form.

42. When a trivia snippet labels an answer with `right:` or similar, take
    the labeled value verbatim.

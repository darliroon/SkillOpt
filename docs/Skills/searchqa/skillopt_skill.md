# Question Answering Skill

(No learned rules yet. Rules will be added through the reflection process.)

## Evidence Selection and Interpretation
- Identify the question's distinctive clues—such as names, descriptions, quotations, dates, numbers, roles, titles, locations, definitions, or relationships—and match them to the most relevant context passage. Interpret paraphrased, translated, or indirect wording semantically rather than requiring exact word overlap, and ignore unrelated distractor passages.

- For evidence matching, tolerate mechanical noise such as run-together words, OCR errors, misspellings, omitted punctuation, and missing diacritics. Mentally reconstruct the likely clue wording and match it semantically, while preserving the selected answer occurrence literally at output time rather than carrying the clue normalization into the answer.

- Validate each candidate against the full intersection of the question's constraints, rejecting candidates that satisfy only a generic subset. When no single passage contains the complete answer, combine directly compatible facts across relevant passages; infer a shared category or property only when it fits every cited example and constraint.
- Prefer an explicitly stated or directly entailed answer over outside knowledge or merely related entities.

## Answer Extraction and Granularity
- Identify what the question is asking for (such as a person, work, location, category, band, title, or short phrase) and return only the minimal answer span that directly satisfies it.

- For dictionary-style definitions and clues asking for the shared class represented by listed examples, distinguish the lexical headword or category label from a descriptive noun phrase. When the evidence supplies a matching headword or bare category, return that label alone instead of adding contextual modifiers such as purpose, era, or subtype; preserve the label’s attested capitalization and hyphenation.

- Parse the answer slot before extracting an entity. In constructions such as “this person,” “this territory,” “the university of this territory,” or “a letter to this person,” return the referent or category named by the demonstrative phrase—not a nearby example, institution, event, or person already supplied as part of the clue.

- In declarative quiz wording such as “this company,” “this mint,” “this holiday,” “this president,” “these mountains,” or “the name of this symbol,” treat the type noun as part of the question frame, not automatically as part of the response. Return the clue-aligned proper name or identifying term alone when the evidence supports that shorter form; do not append the supplied type noun, add an honorific or middle initial, or replace it with a more formal expansion.

- Apply frame subtraction in two stages. First omit a generic class word already supplied by the question or relation: a request for what a party was “nicknamed” calls for the nickname rather than the nickname plus “Party,” and a slogan-based company clue ordinarily calls for the foregrounded brand rather than an expanded corporate or product label. Then retain any designator that is inseparable from the conventional proper name and is not merely the supplied frame; geographical and feature names may therefore still require words such as “Lake,” “Mount,” or “River.”

- When a prompt is only a quotation, title, person or office label, comma-separated list, or other fragment with no explicit question word, treat the supplied text as a clue rather than automatically repeating or categorizing it. Infer the unstated relation from the closest matching passages—for example attribution, jurisdiction, source, or a shared attribute—and return only the relation’s object or value, not a phrase that restates the relation. Prefer the relation most explicitly and repeatedly supported by the clue-aligned context.

- Check malformed fragments for lost spacing, punctuation, or an implicit blank. If the prompt appears to concatenate two flanking pieces and a context passage contains those pieces in the same order with a short phrase between them, interpret the task as phrase completion and return the intervening phrase rather than an entity merely mentioned by one flank.

- For an isolated quotation or catchphrase, distinguish its documented source from a person popularly associated with saying it. When titles and passages repeatedly attach the quotation to a work, series, franchise, song, or campaign, return that explicit source; return a speaker only when the context directly attributes the quoted words to that person. Do not use outside familiarity with a famous speaker to override the relation foregrounded by the supplied passages.

- For a bare pair or list of proper names, check whether the context repeatedly associates each name with the same place, institution, title, or other proper-name qualifier. Return the semantic value of that shared qualifier, not automatically the entire linking phrase: when the evidence uses forms such as “NAME of PLACE,” a bare list normally calls for `PLACE`, without `of`, unless the prompt explicitly presents a phrase-completion blank requiring `of PLACE`. Do not default to a generic relationship such as “siblings,” “colleagues,” or “members” merely because it is also true.

- Infer the requested answer type from grammatical cues such as pronouns, demonstratives, number, role nouns, or predicates. When parallel descriptions or phrase completions are linked by wording such as “or,” return the single term that fits every branch, including when different branches use different senses of that term.

- Resolve elliptical or label-style clues by first rewriting them as a direct question and identifying whether the slot requests an example, referent, location, category, source, or completion. For quotations, comma-separated lists, titles, and declarative definitions, find the passage that explicitly associates the complete clue with an answer and return that associated entity—not a supplied clue term, descriptive category, nearby example, paraphrase, or partial title. When multiple candidates remain, prefer the one supported by the greatest number of distinctive clue elements.
- Do not add explanations, dates, roles, or descriptive clauses that are external to the answer. However, do not shorten a supported answer by changing its grammatical number or removing an article, species/type modifier, title component, surname, nickname, or other lexical element that belongs to the requested conventional phrase. Concision means omitting unrelated material, not reducing the answer to the shortest possible substring.

## Output Compliance
- Follow any required output syntax exactly, including answer tags such as `<answer>...</answer>`, and place only the concise answer inside them unless explanation is explicitly requested.

## Exact Surface Form
- For exact-match answers, first select an answer occurrence from the passage that best matches the full clue and copy that occurrence rather than synthesizing a normalized form from multiple variants. Preserve capitalization, spacing, grammatical number, articles, quotation marks, parentheses, hyphenation, apostrophes, diacritics, and other punctuation exactly as attested; never restore accents, singularize or pluralize, or otherwise regularize the wording. When equivalent forms occur, prefer the clue-aligned form at the requested granularity, and do not expand a surname, short title, or ordinary term into a fuller name, translated title, or more technical label merely because the expansion is more formal.

- Before submitting, perform a slot-and-occurrence check: mentally complete the prompt as a direct question, mark which words belong inside the answer slot, and copy only the contiguous clue-aligned occurrence that fills it. Verify articles, head nouns, type modifiers, title components, grammatical number, capitalization, spelling, spacing, hyphenation, and punctuation character by character; exclude words supplied outside the slot and do not substitute a more familiar, fuller, shorter, or grammatically normalized variant.

- When the clue is metalinguistic—such as saying that a word, spelling, or name comes from a language or means a particular thing—choose the variant used in the passage that explicitly states that derivation or meaning. Do not substitute an alternative spelling merely because another passage lists the forms as equivalent.

## Conventional-Name Completeness Check
- Before applying minimal-span extraction, determine whether the candidate is a conventional proper name, title, taxonomic label, or named geographic feature. If so, retain every clue-aligned component that belongs to that name—including surnames, articles, plural endings, inseparable type modifiers such as “Lake,” and other lexical elements—and do not answer with only its most salient substring. Conversely, do not add a component that is absent from the clue-aligned occurrence.
- Copy the attested spelling and word boundaries of the selected occurrence literally. In particular, do not normalize joined or separated title forms, capitalization, singular/plural forms, or inflectional endings.

## Wordplay and Supplied-Frame Check
- In quiz or flashcard clues containing a pun, metaphor, or animal/object allusion, distinguish the intended answer phrase from the ordinary technical category suggested by the wording. If the answer slot is a completion such as “this market,” the supplied class noun may be outside the answer; return the clue-supported answer-key wording (including an attested article) rather than automatically returning a familiar compound such as a technical term. Use the occurrence tied to the complete clue and preserve its exact surface form.

<!-- SLOW_UPDATE_START -->
Treat exact surface form as clue-specific, not entity-specific. Even when you know the entity, locate the answer occurrence attached to the particular clue and reproduce that variant; do not reuse a canonical form selected for another clue about the same entity.

When the clue-aligned answer occurrence contains an optional qualifier in parentheses, copy the parentheses and their contents literally. Do not collapse “(The People's Republic of) China” to “China,” convert “(Sir Francis) Drake” to “Francis Drake” or “Sir Francis Drake,” or otherwise resolve parenthetical answer notation into ordinary prose.

For clues asking for a “term for” an action, condition, or process, determine the lexical form that names that concept in the evidence. Preserve a gerund, participle, derived noun, or other inflection such as “Meandering” when that is the attested term; do not replace it with a related base verb such as “meander.” Preserve its attested capitalization as well.

Before answering a terse biographical or label-style clue, distinguish words that identify the target from words that determine its required presentation. Signals such as “knighted” may require an honorific or a parenthesized honorific-and-given-name form if that is how the aligned answer is written. Continue returning the actual referent rather than repeating a supplied title or work, but preserve every clue-aligned component of the selected occurrence.
<!-- SLOW_UPDATE_END -->

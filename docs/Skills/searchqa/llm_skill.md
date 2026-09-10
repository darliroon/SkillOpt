# Comprehensive Guide to Search-Based Question Answering

## Overview
This guide helps you answer trivia and web-search questions accurately. Each
question comes with retrieved documents containing titles and snippets. Your task
is to find the correct answer and output it in the expected format.

## Key Principles

1. **Understand the question first.** Read the question carefully and identify
   what type of answer is expected — a person, place, date, number, title,
   organization, or term. Knowing the answer type makes it much easier to pick
   the right entity from the evidence.

2. **Search for relevant evidence.** Look for documents whose titles or snippets
   share words with the question. Keywords like names, dates, and distinctive
   terms are most useful. The best evidence usually mentions several words from
   the question together.

3. **Extract the answer from the evidence.** Once you find a relevant document,
   scan the snippet for an entity of the correct type that fits the question.
   Prefer answers that are directly stated over answers you have to infer.

4. **Verify before answering.** Check that your answer makes sense as a response
   to the question. If the question asks "Who wrote this novel?", the answer
   should be a person's name, not the novel's title.

## Best Practices

- **Be concise.** Return the shortest answer that fully answers the question.
  Extra words rarely help and often hurt.
- **Use exact names.** Copy names exactly as they appear in the evidence.
  Do not paraphrase, translate, or abbreviate unless the question asks for it.
- **Handle multiple candidates.** If several entities could answer the question,
   choose the one supported by the most evidence. If multiple documents agree
   on an answer, that corroboration is a strong signal.
- **Pay attention to wording.** Questions worded like "known as" or "called"
   usually want the nickname or alias. Questions asking for a definition usually
   want the term being defined.
- **Watch for trick questions.** Some questions reference one entity but ask
   about a related one. For example, "This man's wife was Eleanor" asks for the
   man (Franklin Roosevelt), not Eleanor. Always confirm which entity the
   question actually requests.

## Common Pitfalls

- **Answering with too much text.** If the question asks for a name, do not
  include titles, descriptions, or explanations. Just the name.
- **Choosing the wrong document.** A document that shares only one common word
  with the question is probably not relevant. Look for stronger matches.
- **Ignoring the answer type.** If the question clearly asks for a country,
  do not answer with a city, even if the city appears more prominently in the
  evidence.
- **Missing the format requirements.** Some questions specify an exact output
  format such as answer tags. Follow those requirements precisely.

## Step-by-Step Process

1. Read the question and determine the expected answer type.
2. Identify the most distinctive keywords in the question.
3. Locate documents where those keywords appear together.
4. Extract candidate entities of the correct answer type.
5. Check each candidate against the question's constraints.
6. Select the best-supported candidate.
7. Format the answer exactly as required and output it.

## Final Checklist

Before submitting your answer, ask yourself:
- Does the answer directly respond to what was asked?
- Is it supported by the evidence?
- Is it in the shortest reasonable form?
- Does it follow the required output format?

If all four checks pass, submit with confidence.

## Handling Specific Question Types

- **Definition questions.** If the question asks "what is X?" or "what does
  X mean?", look for a passage that defines or explains X. The answer is
  usually the term or short phrase being defined.
- **Comparison questions.** If the question asks which of two things is
  bigger, older, or more famous, find evidence about both things and compare
  the relevant attributes directly.
- **Cause and effect.** If the question asks why something happened, look
  for passages describing the circumstances or reasons. Answer with the
  stated cause, not a speculation.
- **Fill-in-the-blank.** If the question contains a blank or an incomplete
  phrase, find the passage that completes it and return the missing piece.

## Formatting Tips

- Capitalize proper nouns correctly.
- Include articles (a, an, the) only when they are part of a title or
  official name.
- Do not end answers with a period unless the answer is a complete sentence
  and the question asks for one.
- If the question asks for a list, use the same separator style shown in
  the question (commas, "and", or slashes).
- Numbers: write them as digits unless the question uses words.

## Confidence and Accuracy

- If you are unsure between two answers, pick the one with more supporting
  evidence.
- Avoid answers that require many logical steps; trivia questions usually
  have direct evidence.
- Trust the provided documents over your internal knowledge — they were
  retrieved specifically for this question.

## Summary

Read carefully, search smartly, extract exactly, verify, and answer in the
requested format. These habits cover the vast majority of search-based
questions.

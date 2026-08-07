"""Prompts per question type; the LLM writes stems, never answers (§7)."""

import json

SYSTEM = (
    "You are an experienced TOEFL ITP item writer. Respond with a single "
    "JSON object exactly matching the requested schema. No markdown, no "
    "extra keys, no commentary.")


def cloze_prompt(target: dict, options: list[str]) -> str:
    sense = target["sense"]
    banned = [o for o in options if o != target["word"]]
    return f"""Write one cloze sentence testing the word "{target['word']}".

Word sense to test: {sense.get('part_of_speech', '')} — {sense.get('gloss', '')}
{f"English definition: {sense['definition_en']}" if sense.get('definition_en') else ''}

Rules:
- The sentence must contain exactly one blank written as ______ (six underscores) where "{target['word']}" fits naturally.
- 8 to 35 words, academic but accessible tone (TOEFL ITP register).
- The sentence must NOT contain the word "{target['word']}" or any of its inflections.
- The sentence must NOT contain any of these words: {json.dumps(banned)}.
- The context must make "{target['word']}" clearly the best fit among typical confusable words.

Return JSON: {{"sentence": "...", "explanation": "..."}}
"explanation" is in Traditional Chinese (繁體中文): why the target word fits, and one short note on why each distractor ({json.dumps(banned)}) does not."""


def synonym_prompt(target: dict, options: list[str],
                   answer_index: int) -> str:
    sense = target["sense"]
    answer = options[answer_index]
    banned = [o for o in options if o != answer]
    return f"""Write one sentence that uses the word "{target['word']}" in this specific sense:

Sense: {sense.get('part_of_speech', '')} — {sense.get('gloss', '')}
{f"English definition: {sense['definition_en']}" if sense.get('definition_en') else ''}
The correct answer of this synonym question will be "{answer}" — in your sentence,
"{target['word']}" must be replaceable by "{answer}" with the meaning preserved.

Rules:
- The sentence must contain "{target['word']}" (inflected forms allowed).
- 8 to 35 words, TOEFL ITP register.
- The context must clearly force the sense synonymous with "{answer}" and rule out
  other senses of the word.
- The sentence must NOT contain any of these words: {json.dumps(banned + [answer])}.

Return JSON: {{"sentence": "...", "explanation": "..."}}
"explanation" is in Traditional Chinese (繁體中文): what the word means in this context
and why "{answer}" is the closest synonym."""


def structure_prompt(target: dict) -> str:
    example = target["example"].get("sentence", "")
    return f"""Write one TOEFL ITP Structure question testing this grammar point:

Grammar point: {target['name']} ({target['category']})
Description: {target['description']}
Allowed error patterns (wrong options MUST each match one of these, verbatim):
{json.dumps(target['error_patterns'], ensure_ascii=False)}
Style example: {example}

Rules:
- Write a full correct sentence, then blank out one part as ______ .
- "correct_option" restores the full sentence exactly when substituted for the blank.
- Exactly 3 wrong options; each cites its error_pattern verbatim from the list above.
- All four options are pairwise different.

Return JSON:
{{"full_sentence": "...", "stem": "... ______ ...", "correct_option": "...",
  "wrong_options": [{{"text": "...", "error_pattern": "..."}}, ...],
  "explanation": "..."}}
"explanation" is in Traditional Chinese (繁體中文)."""


def written_expression_prompt(target: dict) -> str:
    return f"""Write one TOEFL ITP Written Expression (error identification) question.

Grammar point: {target['name']} ({target['category']})
Description: {target['description']}
The error MUST be of this pattern (verbatim): {target['error_pattern']}

Rules:
- Write a CORRECT sentence (12-30 words, academic register): "correct_version".
- Choose 4 non-overlapping substrings of it as segments A-D, in left-to-right order.
- Pick one segment (index 0-3) and rewrite it INCORRECTLY per the error pattern;
  put the wrong text in "segments" at that index, and the original correct text
  in "corrected_segment".
- The other 3 segments appear in "segments" exactly as in "correct_version".
- Replacing segments[wrong_index] with "corrected_segment" must reproduce
  "correct_version" exactly.

Return JSON:
{{"correct_version": "...", "segments": ["...", "...", "...", "..."],
  "wrong_index": 0, "corrected_segment": "...",
  "error_pattern": {json.dumps(target['error_pattern'], ensure_ascii=False)},
  "explanation": "..."}}
"explanation" is in Traditional Chinese (繁體中文)."""


def build_prompt(target: dict, options: list[str] | None,
                 question_type: str, answer_index: int | None = None) -> str:
    if question_type == "cloze":
        return cloze_prompt(target, options)
    if question_type == "synonym":
        return synonym_prompt(target, options, answer_index)
    if question_type == "structure":
        return structure_prompt(target)
    if question_type == "written_expression":
        return written_expression_prompt(target)
    raise ValueError(f"unknown question type: {question_type}")


async def generate(provider, target: dict, options: list[str] | None,
                   question_type: str, retry_hint: str = "",
                   answer_index: int | None = None) -> dict:
    prompt = build_prompt(target, options, question_type, answer_index)
    if retry_hint:
        prompt += f"\n\nYour previous attempt was rejected: {retry_hint}. Fix it."
    return await provider.complete_json(question_type, SYSTEM, prompt)

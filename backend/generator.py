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
- If the word right before the blank would be "a" or "an", write it as "a/an" instead
  (so the article does not give away the answer's first sound).

Return JSON:
{{"sentence": "...", "translation": "...",
  "option_notes": {{{', '.join(f'{json.dumps(o)}: "..."' for o in options)}}},
  "reasoning": "..."}}
All of "translation", "option_notes" values, and "reasoning" are in Traditional
Chinese (繁體中文):
- "translation": 題目句（含正確答案填入後）的中文翻譯。
- "option_notes": 每個選項單字的簡短中文釋義（詞性＋意思）。
- "reasoning": 為什麼正確答案最合適、其他選項為何不合適。"""


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

Return JSON:
{{"sentence": "...", "translation": "...",
  "option_notes": {{{', '.join(f'{json.dumps(o)}: "..."' for o in options)}}},
  "reasoning": "..."}}
All of "translation", "option_notes" values, and "reasoning" are in Traditional
Chinese (繁體中文):
- "translation": 題目句的中文翻譯。
- "option_notes": 每個選項單字的簡短中文釋義（詞性＋意思）。
- "reasoning": "{target['word']}" 在此語境的意思，以及為什麼 "{answer}" 是最接近的同義詞。"""


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
- Each segment is a SHORT phrase of 1 to 4 words. Segments must NOT be adjacent:
  leave at least one plain (non-underlined) word between consecutive segments,
  and never segment the whole sentence.
- The wrong segment must be UNAMBIGUOUSLY incorrect: a native speaker would mark it
  as an outright grammatical error. Never rely on a subtle meaning difference, style,
  or a merely less idiomatic wording — the original and the wrong version must not
  both be acceptable English.
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

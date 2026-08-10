"""Rule-based validation of LLM output; bad data never reaches the user (§7)."""

import re

BLANK = "______"


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text))


def _contains_word(text: str, word: str, inflections: bool = True) -> bool:
    stem = re.escape(word.lower())
    if inflections and len(word) > 3:
        pattern = rf"\b{stem}\w*"
    else:
        pattern = rf"\b{stem}\b"
    return re.search(pattern, text.lower()) is not None


def _check_vocab_explanation(raw: dict, options: list[str]) -> str | None:
    if not raw.get("translation"):
        return "translation is empty"
    if not raw.get("reasoning"):
        return "reasoning is empty"
    notes = raw.get("option_notes")
    if not isinstance(notes, dict):
        return "option_notes must be an object"
    missing = [o for o in options if not notes.get(o)]
    if missing:
        return f"option_notes missing entries for {missing}"
    return None


def check_cloze(raw: dict, target: dict, options: list[str]) -> str | None:
    sentence = raw.get("sentence", "")
    if not isinstance(sentence, str) or sentence.count(BLANK) != 1:
        return "sentence must contain exactly one ______ blank"
    if not 8 <= _word_count(sentence) <= 35:
        return "sentence must be 8-35 words"
    if re.search(rf"(?<![/\w])[Aa]n?\s+{BLANK}", sentence):
        return ("the article before the blank must be written as 'a/an', "
                "not 'a' or 'an' (it leaks the answer's first sound)")
    if _contains_word(sentence, target["word"]):
        return f"sentence leaks the target word '{target['word']}'"
    for opt in options:
        if opt != target["word"] and _contains_word(sentence, opt,
                                                    inflections=False):
            return f"sentence contains the distractor '{opt}'"
    return _check_vocab_explanation(raw, options)


def check_synonym(raw: dict, target: dict, options: list[str]) -> str | None:
    sentence = raw.get("sentence", "")
    if not isinstance(sentence, str):
        return "sentence missing"
    if not _contains_word(sentence, target["word"]):
        return f"sentence must contain the target word '{target['word']}'"
    if not 8 <= _word_count(sentence) <= 35:
        return "sentence must be 8-35 words"
    for opt in options:
        if _contains_word(sentence, opt, inflections=False):
            return f"sentence contains the option '{opt}'"
    return _check_vocab_explanation(raw, options)


def check_structure(raw: dict, target: dict) -> str | None:
    stem = raw.get("stem", "")
    full = raw.get("full_sentence", "")
    correct = raw.get("correct_option", "")
    wrong = raw.get("wrong_options", [])
    if not (isinstance(stem, str) and isinstance(full, str)
            and isinstance(correct, str) and isinstance(wrong, list)):
        return "missing or mistyped fields"
    if stem.count(BLANK) != 1:
        return "stem must contain exactly one ______ blank"
    if len(wrong) != 3:
        return "exactly 3 wrong options required"
    texts = [correct] + [w.get("text", "") for w in wrong]
    if len({t.strip().lower() for t in texts}) != 4:
        return "options must be pairwise different"
    restored = stem.replace(BLANK, correct)
    if _normalise(restored) != _normalise(full):
        return "correct_option does not restore full_sentence"
    allowed = set(target["error_patterns"])
    for w in wrong:
        if w.get("error_pattern") not in allowed:
            return (f"error_pattern '{w.get('error_pattern')}' is not in the "
                    f"allowed list")
    if not raw.get("explanation"):
        return "explanation is empty"
    return None


def check_written_expression(raw: dict, target: dict) -> str | None:
    correct_version = raw.get("correct_version", "")
    segments = raw.get("segments", [])
    wrong_index = raw.get("wrong_index")
    corrected = raw.get("corrected_segment", "")
    if not (isinstance(correct_version, str) and isinstance(segments, list)
            and isinstance(corrected, str) and isinstance(wrong_index, int)):
        return "missing or mistyped fields"
    if len(segments) != 4 or not 0 <= wrong_index <= 3:
        return "need 4 segments and wrong_index in 0-3"
    if raw.get("error_pattern") != target["error_pattern"]:
        return "error_pattern must equal the assigned one"
    if not raw.get("explanation"):
        return "explanation is empty"
    for seg in segments:
        if not isinstance(seg, str) or not seg.strip():
            return "each segment must be a non-empty string"
        if len(seg.split()) > 5:
            return f"segment '{seg}' is too long (max 4-5 words each)"
    if sum(len(s) for s in segments) > 0.6 * len(correct_version):
        return ("segments cover too much of the sentence; keep them short "
                "and leave plain words between them")

    # The displayed sentence: correct_version with the wrong segment swapped in.
    display, offsets = _build_display(correct_version, segments, wrong_index,
                                      corrected)
    if display is None:
        return offsets  # error message
    raw["_display_sentence"] = display
    raw["_segment_offsets"] = offsets
    return None


def _build_display(correct_version: str, segments: list[str],
                   wrong_index: int, corrected: str):
    """Locate the 4 segments left-to-right; swap in the wrong one.
    Returns (display_sentence, [(start, end)]*4) or (None, reason)."""
    correct_texts = [corrected if i == wrong_index else seg
                     for i, seg in enumerate(segments)]
    cursor, spans = 0, []
    for seg in correct_texts:
        pos = correct_version.find(seg, cursor)
        if pos < 0:
            return None, (f"segment '{seg}' not found in correct_version "
                          "in left-to-right order")
        spans.append((pos, pos + len(seg)))
        cursor = pos + len(seg)

    display, offsets, shift = correct_version, [], 0
    for i, ((start, end), shown) in enumerate(zip(spans, segments, strict=True)):
        start += shift
        end += shift
        if i == wrong_index:
            display = display[:start] + shown + display[end:]
            shift += len(shown) - (end - start)
            end = start + len(shown)
        offsets.append((start, end))
    return display, offsets


def check(raw: dict, target: dict, options: list[str] | None,
          question_type: str) -> str | None:
    """Returns None when valid, otherwise a reason string (fed back on retry)."""
    if not isinstance(raw, dict):
        return "output is not a JSON object"
    if question_type == "cloze":
        return check_cloze(raw, target, options)
    if question_type == "synonym":
        return check_synonym(raw, target, options)
    if question_type == "structure":
        return check_structure(raw, target)
    if question_type == "written_expression":
        return check_written_expression(raw, target)
    return f"unknown question type: {question_type}"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()

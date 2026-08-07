"""Local grading for the four objective types. No LLM involved."""

LETTERS = "ABCDE"
IDK = "E"          # "I don't know" — always the last option


def grade(question: dict, answer: str) -> float:
    """answer is a letter A-E; returns 1.0 or 0.0."""
    answer = (answer or "").strip().upper()
    if answer not in LETTERS:
        return 0.0
    if answer == IDK:
        return 0.0
    return 1.0 if LETTERS.index(answer) == question["answer_index"] else 0.0

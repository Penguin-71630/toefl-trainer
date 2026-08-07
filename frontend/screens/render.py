"""Shared text rendering: written-expression underline layout, review entries."""

from rich.text import Text

LETTERS = "ABCDE"


def wrap_with_offsets(text: str, width: int) -> list[tuple[int, int]]:
    """Word-wrap, keeping each visual line's (start, end) in the original
    string so column arithmetic for the letter row stays correct."""
    lines, start = [], 0
    while start < len(text):
        if len(text) - start <= width:
            lines.append((start, len(text)))
            break
        cut = text.rfind(" ", start, start + width + 1)
        if cut <= start:
            cut = start + width
        lines.append((start, cut))
        start = cut + 1
    return lines


def render_written_expression(sentence: str, offsets: list[list[int]],
                              width: int,
                              extra_styles: list[tuple[int, int, str]]
                              | None = None) -> Text:
    """Sentence with 4 underlined segments + a letter row (A-D) under each
    segment's centre. extra_styles: additional (start, end, style) spans."""
    out = Text()
    for ls, le in wrap_with_offsets(sentence, width):
        line = Text(sentence[ls:le])
        letter_row = [" "] * max(le - ls, 1)
        for i, (ss, se) in enumerate(offsets):
            s, e = max(ss, ls), min(se, le)
            if s >= e:
                continue
            line.stylize("underline", s - ls, e - ls)
            col = (s - ls + e - ls - 1) // 2
            letter_row[min(col, len(letter_row) - 1)] = LETTERS[i]
        for ss, se, style in extra_styles or []:
            s, e = max(ss, ls), min(se, le)
            if s < e:
                line.stylize(style, s - ls, e - ls)
        out.append(line)
        out.append("\n")
        out.append("".join(letter_row).rstrip() + "\n")
    return out


def render_review_entry(number: int, entry: dict) -> str:
    """One wrong-answer entry as Rich markup (for the review list page)."""
    lines = [f"[red]<{number}. {entry['question_type']}  "
             f"{entry['answered_at'][:16].replace('T', ' ')}>[/red]"]
    if entry["question_type"] == "synonym" and entry.get("word"):
        lines.append(f'  The word [bold]"{entry["word"]}"[/bold] '
                     "is closest in meaning to:")
    sentence = entry.get("sentence") or ""
    if entry["question_type"] == "written_expression" and \
            entry.get("segment_offsets"):
        text = render_written_expression(sentence, entry["segment_offsets"],
                                         width=76)
        indented = "\n".join("  " + ln for ln in text.markup.split("\n"))
        lines.append(indented)
    else:
        lines.append(f"  {sentence}")
    if entry.get("options"):
        opts = "   ".join(f"({LETTERS[i]}) {o}"
                          for i, o in enumerate(entry["options"]))
        lines.append(f"  {opts}")
    lines.append(f"  你的答案: {entry['your_answer']}   "
                 f"正解: [green]{entry['correct_answer']}[/green]")
    if entry.get("gloss"):
        lines.append(f"  [dim]{entry.get('word', '')}: {entry['gloss']}[/dim]")
    if entry.get("explanation"):
        lines.append(f"  [dim]{entry['explanation']}[/dim]")
    lines.append("")
    return "\n".join(lines)

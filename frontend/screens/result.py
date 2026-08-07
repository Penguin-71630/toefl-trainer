"""RESULT (merged with REVIEW): rating change on top, then every question
with your answer, the correct answer, and the explanation."""

from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from frontend.screens.quiz import TYPE_TITLES
from frontend.screens.render import LETTERS, render_written_expression


class ResultScreen(Screen):
    BINDINGS = [
        ("q,enter,escape", "back", "Return to menu"),
        ("j,down", "scroll(1)", "Scroll down"),
        ("k,up", "scroll(-1)", "Scroll up"),
    ]

    def __init__(self, quiz: dict, result: dict, answers: dict, elapsed: int):
        super().__init__()
        self.quiz = quiz
        self.result = result
        self.elapsed = elapsed

    def compose(self):
        with VerticalScroll(id="result-body"):
            yield Static(self._render_result(), id="result-text")

    def _render_result(self) -> str:
        r = self.result
        rt = r["rating"]
        sign = "+" if rt["delta"] >= 0 else ""
        title = TYPE_TITLES.get(self.quiz["question_type"], "Quiz")
        lines = [
            "[dim](Q|ENTER|ESC) [RETURN TO MENU]    j/k/↑/↓ 捲動[/dim]",
            "",
            f"[bold]{title}[/bold]"
            f"{' ' * 4}(Time Used: {self.elapsed // 60:02d}:"
            f"{self.elapsed % 60:02d})",
            "",
            f"[bold]Score: {r['score']} / {r['total']}[/bold]",
            f"[bold]{rt['before']} → {rt['after']} ({sign}{rt['delta']})  "
            f"{rt['rank']}[/bold]   [dim]≈ TOEFL {rt['estimated_toefl']}[/dim]",
            "",
        ]
        for q in r["questions"]:
            n = q["q_index"] + 1
            if q["correct"]:
                lines.append(f"[green]<Question {n}: Correct>[/green]")
            else:
                lines.append(f"[red]<Question {n}: Wrong>[/red]")
            if q["question_type"] == "written_expression" and \
                    q.get("segment_offsets"):
                text = render_written_expression(
                    q["sentence"], q["segment_offsets"], width=76)
                lines.append("\n".join(
                    "  " + ln for ln in text.markup.split("\n")))
            else:
                lines.append(f"  {q['sentence']}")
            if q["question_type"] == "synonym" and q.get("word"):
                lines.append(f'  The word [bold]"{q["word"]}"[/bold] '
                             "is closest in meaning to:")
            if q.get("options"):
                lines.append("  " + "   ".join(
                    f"({LETTERS[i]}) {o}" for i, o in enumerate(q["options"])))
            your = q["your_answer"]
            shown = your if your != "E" else "E (I don't know)"
            lines.append(f"  你的答案: {shown}   "
                         f"正解: [green]{q['correct_answer']}[/green]")
            if q.get("corrected_segment"):
                lines.append(f"  [dim]正確寫法: {q['corrected_segment']}[/dim]")
            if q.get("gloss"):
                lines.append(f"  [dim]{q.get('word', '')}: {q['gloss']}[/dim]")
            if q.get("explanation"):
                body = "\n".join("  " + ln
                                 for ln in q["explanation"].split("\n"))
                lines.append(f"[dim]{body}[/dim]")
            lines.append("")
        return "\n".join(lines)

    def action_back(self) -> None:
        from frontend.screens.menu import MenuScreen
        self.app.switch_screen(MenuScreen())

    def action_scroll(self, step: int) -> None:
        body = self.query_one("#result-body", VerticalScroll)
        body.scroll_relative(y=step * 2, animate=False)

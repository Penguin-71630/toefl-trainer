"""QUIZ: answer with a-e, TAB between questions, h/l moves the markable-word
cursor, ENTER marks a word as unfamiliar, s opens submit confirmation.
q is deliberately NOT bound — you cannot quit mid-quiz."""

import time

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Label, Static

from frontend import api
from frontend.screens.render import render_written_expression

LETTERS = "ABCDE"
TYPE_TITLES = {
    "cloze": "Cloze Quiz",
    "synonym": "Synonym Quiz",
    "structure": "Structure Quiz",
    "written_expression": "Written Expression Quiz",
}
MARK_STYLE = "bold red"
CURSOR_STYLE = "on grey37"


class SubmitConfirm(ModalScreen[bool]):
    """YES/NO confirmation, hover starts on NO."""

    BINDINGS = [
        ("left,h", "move", "Move"),
        ("right,l", "move", "Move"),
        ("enter", "choose", "Choose"),
        ("escape,q", "dismiss(False)", "Cancel"),
    ]

    def __init__(self, unanswered: int):
        super().__init__()
        self.unanswered = unanswered
        self.yes = False

    def compose(self):
        message = "確定要交卷嗎？"
        if self.unanswered:
            message += f"（還有 {self.unanswered} 題未作答，將以 0 分計）"
        with Vertical(id="confirm-box"):
            yield Label(message)
            with Horizontal(id="confirm-buttons"):
                yield Static(" YES ", id="confirm-yes")
                yield Static(" NO ", id="confirm-no")

    def on_mount(self) -> None:
        self._paint()

    def _paint(self) -> None:
        self.query_one("#confirm-yes").set_class(self.yes, "confirm-hover")
        self.query_one("#confirm-no").set_class(not self.yes, "confirm-hover")

    def action_move(self) -> None:
        self.yes = not self.yes
        self._paint()

    def action_choose(self) -> None:
        self.dismiss(self.yes)


class QuizScreen(Screen):
    BINDINGS = [
        Binding("tab", "next_q(1)", "Next", priority=True),
        Binding("shift+tab", "next_q(-1)", "Prev", priority=True),
        ("a", "answer('A')", "A"), ("b", "answer('B')", "B"),
        ("c", "answer('C')", "C"), ("d", "answer('D')", "D"),
        ("e", "answer('E')", "E"),
        ("h,left", "cursor(-1)", "Word left"),
        ("l,right", "cursor(1)", "Word right"),
        ("enter", "mark", "Mark word"),
        ("s", "submit", "Submit"),
    ]

    def __init__(self, quiz: dict):
        super().__init__()
        self.quiz = quiz
        self.questions = quiz["questions"]
        self.current = 0
        self.answers: dict[int, str] = {}
        self.marks: set[tuple[int, int]] = set()     # (q_index, markable idx)
        self.cursors: dict[int, int] = {}
        self.started = time.monotonic()

    # ------------------------------------------------------------ layout

    def compose(self):
        title = TYPE_TITLES.get(self.quiz["question_type"], "Quiz")
        with Horizontal(id="quiz-header"):
            yield Label(title, id="quiz-title")
            yield Label("(Time Elapsed: 00:00)", id="quiz-timer")
        yield Static("", id="quiz-progress")
        yield Static("", id="quiz-question")
        yield Static("", id="quiz-options")
        yield Static(
            "[dim]a-e 作答  TAB 跳題  h/l 移動游標  ENTER 標記不熟  "
            "s 交卷[/dim]", id="quiz-help")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._paint()

    def _tick(self) -> None:
        elapsed = int(time.monotonic() - self.started)
        self.query_one("#quiz-timer", Label).update(
            f"(Time Elapsed: {elapsed // 60:02d}:{elapsed % 60:02d})")

    # ------------------------------------------------------------ paint

    def _paint(self) -> None:
        q = self.questions[self.current]
        answered = len(self.answers)
        self.query_one("#quiz-progress", Static).update(
            f"<Question {self.current + 1} / {len(self.questions)}>   "
            f"answered: {answered}/{len(self.questions)}")

        self.query_one("#quiz-question", Static).update(
            self._render_question(q))
        self.query_one("#quiz-options", Static).update(self._render_options(q))

    def _mark_spans(self, q: dict) -> list[tuple[int, int, str]]:
        """Marked words first, cursor last — user marks win visually, and the
        cursor is visible on top of both."""
        spans = []
        for m_idx, m in enumerate(q["markable"]):
            if (self.current, m_idx) in self.marks:
                spans.append((m["span"][0], m["span"][1], MARK_STYLE))
        cursor = self.cursors.get(self.current)
        if cursor is not None and q["markable"]:
            m = q["markable"][cursor]
            spans.append((m["span"][0], m["span"][1], CURSOR_STYLE))
        return spans

    def _render_question(self, q: dict) -> Text:
        prefix = Text()
        if q["question_type"] == "synonym":
            prefix.append(f'The word "{q["word"]}" is closest in meaning '
                          "to:\n\n")
        if q["question_type"] == "written_expression":
            body = render_written_expression(
                q["sentence"], q["segment_offsets"],
                width=max(self.size.width - 6, 40),
                extra_styles=self._mark_spans(q))
        else:
            body = Text(q["sentence"])
            for start, end, style in self._mark_spans(q):
                body.stylize(style, start, end)
        return prefix + body

    def _render_options(self, q: dict) -> Text:
        chosen = self.answers.get(self.current)
        out = Text("\n")
        options = q.get("options") or list("ABCD")
        labels = ([f"({LETTERS[i]}) {o}" for i, o in enumerate(options)]
                  if q.get("options")
                  else [f"({letter})" for letter in "ABCD"])
        labels.append("(E) I don't know")
        for i, label in enumerate(labels):
            line = Text("  " + label)
            if chosen == LETTERS[i]:
                line.stylize("reverse", 2, len(line))
            out.append(line)
            out.append("\n")
        return out

    # ------------------------------------------------------------ actions

    def action_answer(self, letter: str) -> None:
        self.answers[self.current] = letter
        self._paint()

    def action_next_q(self, step: int) -> None:
        self.current = (self.current + step) % len(self.questions)
        self._paint()

    def action_cursor(self, step: int) -> None:
        q = self.questions[self.current]
        if not q["markable"]:
            return
        cursor = self.cursors.get(self.current)
        if cursor is None:
            cursor = 0 if step > 0 else len(q["markable"]) - 1
        else:
            cursor = (cursor + step) % len(q["markable"])
        self.cursors[self.current] = cursor
        self._paint()

    def action_mark(self) -> None:
        cursor = self.cursors.get(self.current)
        if cursor is None:
            return
        key = (self.current, cursor)
        if key in self.marks:
            self.marks.discard(key)
        else:
            self.marks.add(key)
        self._paint()

    def action_submit(self) -> None:
        unanswered = len(self.questions) - len(self.answers)

        def on_confirm(yes: bool | None) -> None:
            if yes:
                self.do_submit()

        self.app.push_screen(SubmitConfirm(unanswered), on_confirm)

    @work
    async def do_submit(self) -> None:
        answers = [{"q_index": i, "answer": letter}
                   for i, letter in self.answers.items()]
        marked_ids = sorted({
            self.questions[qi]["markable"][mi]["item_id"]
            for qi, mi in self.marks})
        elapsed = int(time.monotonic() - self.started)
        try:
            result = await api.submit_quiz(self.quiz["quiz_id"], answers,
                                           marked_ids)
        except Exception as exc:
            self.notify(f"交卷失敗：{exc}", severity="error")
            return
        self.app.user["rating"] = result["rating"]["after"]
        self.app.user["rank"] = result["rating"]["rank"]
        from frontend.screens.result import ResultScreen
        self.app.switch_screen(ResultScreen(self.quiz, result, self.answers,
                                            elapsed))

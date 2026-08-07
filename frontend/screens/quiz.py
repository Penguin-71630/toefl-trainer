"""QUIZ: answer with a-e (or ENTER on an option the cursor is on),
n / SHIFT+TAB between questions, h/j/k/l moves the markable-word cursor
(sentence and options), m marks a word as unfamiliar, s opens submit
confirmation. q is deliberately NOT bound — you cannot quit mid-quiz."""

import time

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Label, Static

from frontend import api
from frontend.screens.render import render_written_expression, wrap_with_offsets

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
        ("n", "next_q(1)", "Next"),
        Binding("shift+tab", "next_q(-1)", "Prev", priority=True),
        ("enter", "toggle_option", "Toggle option"),
        ("a", "answer('A')", "A"), ("b", "answer('B')", "B"),
        ("c", "answer('C')", "C"), ("d", "answer('D')", "D"),
        ("e", "answer('E')", "E"),
        ("h,left", "cursor(-1)", "Word left"),
        ("l,right", "cursor(1)", "Word right"),
        ("k,up", "cursor_v(-1)", "Word up"),
        ("j,down", "cursor_v(1)", "Word down"),
        ("m", "mark", "Mark word"),
        ("s", "submit", "Submit"),
    ]

    def __init__(self, quiz: dict):
        super().__init__()
        self.quiz = quiz
        self.questions = quiz["questions"]
        self.current = 0
        self.answers: dict[int, str] = {}
        # (q_index, where, span_start) -> item_id; where is "s" (sentence)
        # or an option index
        self.marks: dict[tuple[int, str | int, int], int] = {}
        self.cursors: dict[int, int] = {}            # q_index -> nav index
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
            "[dim]a-e 作答  ENTER 選游標所在選項  n 下一題  "
            "SHIFT+TAB 上一題  h/j/k/l 移動游標  m 標記不熟  "
            "s 交卷[/dim]", id="quiz-help")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._paint()

    def _tick(self) -> None:
        elapsed = int(time.monotonic() - self.started)
        self.query_one("#quiz-timer", Label).update(
            f"(Time Elapsed: {elapsed // 60:02d}:{elapsed % 60:02d})")

    # ------------------------------------------------------ nav model

    def _wrap_width(self) -> int:
        return max(self.size.width - 6, 40)

    def _nav(self, q: dict) -> list[dict]:
        """Markable positions in visual order: sentence words (with their
        wrapped line/column), then option words. Used by the h/j/k/l
        cursor; up/down picks the horizontally nearest word on the
        nearest other line."""
        width = self._wrap_width()
        prefix_lines = 2 if q["question_type"] == "synonym" else 0
        per_line = 2 if q["question_type"] == "written_expression" else 1
        lines = wrap_with_offsets(q["sentence"], width)
        items = []
        for m in q["markable"]:
            s, e = m["span"]
            for li, (ls, le) in enumerate(lines):
                if ls <= s < le:
                    items.append({
                        "where": "s", "span": (s, e),
                        "item_id": m["item_id"],
                        "line": prefix_lines + li * per_line,
                        "col": (max(s, ls) + min(e, le)) / 2 - ls})
                    break
        base = prefix_lines + len(lines) * per_line + 2
        for oi, opt_marks in enumerate(q.get("options_markable") or []):
            for m in opt_marks:
                s, e = m["span"]
                items.append({"where": oi, "span": (s, e),
                              "item_id": m["item_id"],
                              "line": base + oi, "col": 6 + (s + e) / 2})
        items.sort(key=lambda it: (it["line"], it["col"]))
        return items

    def _cursor_item(self, q: dict) -> dict | None:
        nav = self._nav(q)
        if not nav:
            return None
        return nav[self.cursors.get(self.current, 0) % len(nav)]

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

    def _mark_spans(self, q: dict,
                    where: str | int) -> list[tuple[int, int, str]]:
        """Marked words first, cursor last — user marks win visually, and
        the cursor is visible on top of both."""
        spans = []
        for (qi, w, start), _item in self.marks.items():
            if qi != self.current or w != where:
                continue
            source = (q["markable"] if where == "s"
                      else (q.get("options_markable") or [[]])[where])
            for m in source:
                if m["span"][0] == start:
                    spans.append((m["span"][0], m["span"][1], MARK_STYLE))
        cur = self._cursor_item(q)
        if cur is not None and cur["where"] == where:
            spans.append((cur["span"][0], cur["span"][1], CURSOR_STYLE))
        return spans

    def _render_question(self, q: dict) -> Text:
        prefix = Text()
        if q["question_type"] == "synonym":
            prefix.append(f'The word "{q["word"]}" is closest in meaning '
                          "to:\n\n")
        styles = self._mark_spans(q, "s")
        if q["question_type"] == "written_expression":
            body = render_written_expression(
                q["sentence"], q["segment_offsets"],
                width=self._wrap_width(), extra_styles=styles)
        else:
            # wrap manually so the nav model's line/column arithmetic
            # matches what is displayed
            body = Text()
            for ls, le in wrap_with_offsets(q["sentence"],
                                            self._wrap_width()):
                line = Text(q["sentence"][ls:le])
                for start, end, style in styles:
                    s, e = max(start, ls), min(end, le)
                    if s < e:
                        line.stylize(style, s - ls, e - ls)
                body.append(line)
                body.append("\n")
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
            if q.get("options") and i < len(options):
                for start, end, style in self._mark_spans(q, i):
                    line.stylize(style, start + 6, end + 6)
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

    def action_toggle_option(self) -> None:
        """ENTER: if the cursor sits on an option's word, toggle that
        option as the answer; otherwise do nothing."""
        cur = self._cursor_item(self.questions[self.current])
        if cur is None or cur["where"] == "s":
            return
        letter = LETTERS[cur["where"]]
        if self.answers.get(self.current) == letter:
            del self.answers[self.current]
        else:
            self.answers[self.current] = letter
        self._paint()

    def action_cursor(self, step: int) -> None:
        nav = self._nav(self.questions[self.current])
        if not nav:
            return
        cursor = self.cursors.get(self.current, 0)
        self.cursors[self.current] = (cursor + step) % len(nav)
        self._paint()

    def action_cursor_v(self, step: int) -> None:
        """Move to the horizontally nearest word on the nearest line
        above/below."""
        nav = self._nav(self.questions[self.current])
        if not nav:
            return
        cursor = self.cursors.get(self.current, 0) % len(nav)
        here = nav[cursor]
        other_lines = sorted({it["line"] for it in nav
                              if (it["line"] - here["line"]) * step > 0},
                             reverse=(step < 0))
        if not other_lines:
            return
        target_line = other_lines[0]
        best = min((i for i, it in enumerate(nav)
                    if it["line"] == target_line),
                   key=lambda i: abs(nav[i]["col"] - here["col"]))
        self.cursors[self.current] = best
        self._paint()

    def action_mark(self) -> None:
        cur = self._cursor_item(self.questions[self.current])
        if cur is None:
            return
        key = (self.current, cur["where"], cur["span"][0])
        if key in self.marks:
            del self.marks[key]
        else:
            self.marks[key] = cur["item_id"]
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
        marked_ids = sorted(set(self.marks.values()))
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

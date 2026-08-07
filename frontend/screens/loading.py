"""LOADING_QUIZ: start background generation, poll status, show progress.
q cancels — already-generated questions are banked (no wasted API quota)."""

import asyncio

from textual import work
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Label, ProgressBar

from frontend import api


class LoadingQuizScreen(Screen):
    BINDINGS = [("q,escape", "cancel", "Cancel")]

    def __init__(self, question_type: str, n: int = 10):
        super().__init__()
        self.question_type = question_type
        self.n = n
        self.quiz_id: str | None = None
        self._cancelled = False

    def compose(self):
        with Middle():
            with Center():
                yield Label(f"Generating {self.question_type} quiz...",
                            id="loading-title")
            with Center():
                yield ProgressBar(total=self.n, show_eta=False,
                                  id="loading-bar")
            with Center():
                yield Label(f"0/{self.n}", id="loading-step")
            with Center():
                yield Label("[dim]q 取消（已生成的題目會保留下次用）[/dim]")

    def on_mount(self) -> None:
        self.load()

    @work
    async def load(self) -> None:
        label = self.query_one("#loading-step", Label)
        bar = self.query_one("#loading-bar", ProgressBar)
        try:
            self.quiz_id = await api.start_quiz(
                self.app.user["user_id"], self.question_type, self.n)
            while True:
                if self._cancelled:
                    return
                status = await api.quiz_status(self.quiz_id)
                bar.update(progress=status["ready"], total=status["total"])
                label.update(f"{status['ready']}/{status['total']}"
                             + (f"  (failed: {status['failed']})"
                                if status["failed"] else ""))
                if status["ready"] >= status["total"]:
                    break
                await asyncio.sleep(0.7)
            if status["total"] == 0:
                label.update("[red]題目生成失敗，請稍後再試[/red]")
                return
            quiz = await api.get_quiz(self.quiz_id)
        except Exception as exc:
            label.update(f"[red]Error: {exc}[/red]")
            return
        if self._cancelled:
            return
        from frontend.screens.quiz import QuizScreen
        self.app.switch_screen(QuizScreen(quiz))

    def action_cancel(self) -> None:
        self._cancelled = True
        if self.quiz_id:
            self.bank_and_close(self.quiz_id)
        else:
            self.app.pop_screen()

    @work
    async def bank_and_close(self, quiz_id: str) -> None:
        try:
            await api.abandon_quiz(quiz_id)
        except Exception:
            pass
        self.app.pop_screen()

"""WRONG_ANSWERS_REVIEW: most recent wrong answers from the reviews log."""

from textual import work
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from frontend import api
from frontend.screens.render import render_review_entry


class WrongAnswersScreen(Screen):
    BINDINGS = [("q,escape", "app.pop_screen", "Back")]

    def compose(self):
        with VerticalScroll(id="wrong-body"):
            yield Static("Loading...", id="wrong-text")

    def on_mount(self) -> None:
        self.load()

    @work
    async def load(self) -> None:
        widget = self.query_one("#wrong-text", Static)
        try:
            data = await api.reviews(self.app.user["user_id"],
                                     only_wrong=True, limit=50)
        except Exception as exc:
            widget.update(f"[red]Failed to load reviews: {exc}[/red]")
            return
        entries = data["reviews"]
        if not entries:
            widget.update("目前沒有錯題紀錄。\n\n按 q 返回選單")
            return
        parts = [f"[bold]Wrong Answers Review[/bold]  (最近 {len(entries)} 筆)\n"]
        for i, entry in enumerate(entries, 1):
            parts.append(render_review_entry(i, entry))
        parts.append("按 q 返回選單")
        widget.update("\n".join(parts))

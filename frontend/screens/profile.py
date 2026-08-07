"""USER_PROFILE: rating, rank, estimated TOEFL, per-type answer counts."""

from textual import work
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from frontend import api

TYPE_LABELS = {
    "cloze": "Cloze",
    "synonym": "Synonym",
    "structure": "Structure",
    "written_expression": "Written Expression",
}


class ProfileScreen(Screen):
    BINDINGS = [("q,escape", "app.pop_screen", "Back")]

    def compose(self):
        with VerticalScroll(id="profile-body"):
            yield Static("Loading...", id="profile-text")

    def on_mount(self) -> None:
        self.load()

    @work
    async def load(self) -> None:
        widget = self.query_one("#profile-text", Static)
        try:
            data = await api.stats(self.app.user["user_id"])
        except Exception as exc:
            widget.update(f"[red]Failed to load profile: {exc}[/red]")
            return
        lines = [
            "[bold]User Profile[/bold]",
            "",
            f"  Name             {data['username']}",
            f"  Rating           {data['rating']} ({data['rank']})",
            f"  Estimated TOEFL  {data['estimated_toefl']}  "
            "[dim](僅反映字彙/文法水準)[/dim]",
            f"  Quizzes done     {data['exams_done']}",
        ]
        if data["accuracy"] is not None:
            lines.append(f"  Accuracy         {data['accuracy']:.1%} "
                         f"({data['total_answered']} questions)")
        lines += ["", "[bold]Answered by type[/bold]"]
        for key, label in TYPE_LABELS.items():
            lines.append(f"  {label:<20} {data['answered_by_type'][key]}")
        history = data["rating_history"][-10:]
        if history:
            lines += ["", "[bold]Recent rating[/bold]"]
            for h in history:
                sign = "+" if h["delta"] >= 0 else ""
                lines.append(f"  {h['recorded_at'][:10]}  {h['rating']}  "
                             f"({sign}{h['delta']})")
        if data["weakest_words"]:
            lines += ["", "[bold]Weakest words[/bold]"]
            for w in data["weakest_words"]:
                lines.append(f"  {w['word']:<24} p={w['proficiency']}")
        lines += ["", "按 q 返回選單"]
        widget.update("\n".join(lines))

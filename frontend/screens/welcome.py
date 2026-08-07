"""WELCOME: username login (creates the user on first login)."""

from textual import work
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Input, Label

from frontend import api


class WelcomeScreen(Screen):
    def compose(self):
        with Middle():
            with Center():
                yield Label("Welcome to TOEFL Trainer", id="welcome-title")
            with Center():
                yield Input(placeholder="Enter your username",
                            max_length=40, id="username")
            with Center():
                yield Label("", id="welcome-error")

    def on_mount(self) -> None:
        self.query_one("#username", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        username = event.value.strip()
        if not username:
            self.query_one("#welcome-error", Label).update(
                "[red]Username cannot be empty[/red]")
            return
        self.login(username)

    @work
    async def login(self, username: str) -> None:
        error = self.query_one("#welcome-error", Label)
        try:
            user = await api.login(username)
        except Exception as exc:
            error.update(f"[red]Login failed: {exc}[/red]")
            return
        self.app.user = {"user_id": user["user_id"], "username": username,
                         "rating": user["rating"], "rank": user["rank"]}
        from frontend.screens.menu import MenuScreen
        self.app.switch_screen(MenuScreen())

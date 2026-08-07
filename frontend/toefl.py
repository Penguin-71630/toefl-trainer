"""TOEFL trainer — Textual CLI frontend. Run backend first (see run.py)."""

from textual.app import App

from frontend.screens.startup import StartupScreen


class ToeflApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "TOEFL Trainer"

    def __init__(self):
        super().__init__()
        self.user: dict = {}

    def on_mount(self) -> None:
        self.push_screen(StartupScreen())


def main() -> None:
    ToeflApp().run()


if __name__ == "__main__":
    main()

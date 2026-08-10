"""MENU: grouped entries (Quiz / User / Rating), j/k or arrow navigation."""

from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

QUIZ_TYPES = [
    ("cloze", "Cloze — 字彙填空"),
    ("synonym", "Synonym — 同義詞"),
    ("structure", "Structure — 句構選擇"),
    ("written_expression", "Written Expression — 挑錯"),
]

ENTRIES = (
    [("group", "Quiz")]
    + [("quiz", key, label) for key, label in QUIZ_TYPES]
    + [("group", "User"),
       ("page", "profile", "User Profile"),
       ("page", "wrong", "Wrong Answers Review"),
       ("group", "Rating"),
       ("page", "quiz_help", "Question Types 說明"),
       ("page", "rating_help", "Rating System 說明")]
)


class MenuScreen(Screen):
    BINDINGS = [
        ("j,down", "move(1)", "Down"),
        ("k,up", "move(-1)", "Up"),
        ("enter", "choose", "Select"),
    ]

    def __init__(self):
        super().__init__()
        self.items = [(i, e) for i, e in enumerate(ENTRIES)
                      if e[0] != "group"]
        self.cursor = 0

    def compose(self):
        user = self.app.user
        with Middle():
            with Center():
                yield Label(
                    f"{user['username']}   {user['rating']} "
                    f"({user['rank']})", id="menu-user")
            with Center():
                yield Vertical(*self._rows(), id="menu-list")
            with Center():
                yield Static(
                    "[dim]j/k/↑/↓ 移動選單  ENTER 進入該功能  "
                    "Ctrl+Q 退出[/dim]", id="menu-help")

    def _rows(self):
        rows = []
        for i, entry in enumerate(ENTRIES):
            if entry[0] == "group":
                rows.append(Static(f"[bold]{entry[1]}[/bold]",
                                   classes="menu-group"))
            else:
                rows.append(Static(entry[-1], classes="menu-item",
                                   id=f"menu-{i}"))
        return rows

    def on_mount(self) -> None:
        self._highlight()

    def _highlight(self) -> None:
        for pos, (i, _) in enumerate(self.items):
            widget = self.query_one(f"#menu-{i}", Static)
            widget.set_class(pos == self.cursor, "menu-hover")

    def action_move(self, step: int) -> None:
        self.cursor = (self.cursor + step) % len(self.items)
        self._highlight()

    def action_choose(self) -> None:
        entry = self.items[self.cursor][1]
        if entry[0] == "quiz":
            from frontend.screens.loading import LoadingQuizScreen
            self.app.push_screen(LoadingQuizScreen(entry[1]))
        elif entry[1] == "profile":
            from frontend.screens.profile import ProfileScreen
            self.app.push_screen(ProfileScreen())
        elif entry[1] == "wrong":
            from frontend.screens.wrong import WrongAnswersScreen
            self.app.push_screen(WrongAnswersScreen())
        elif entry[1] == "quiz_help":
            from frontend.screens.instruction import QuizInstructionScreen
            self.app.push_screen(QuizInstructionScreen())
        elif entry[1] == "rating_help":
            from frontend.screens.instruction import RatingInstructionScreen
            self.app.push_screen(RatingInstructionScreen())

    def on_screen_resume(self) -> None:
        self.refresh_user()

    def refresh_user(self) -> None:
        user = self.app.user
        self.query_one("#menu-user", Label).update(
            f"{user['username']}   {user['rating']} ({user['rank']})")

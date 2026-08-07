"""STARTUP: stepwise progress while checking the backend, then WELCOME."""

import asyncio

from textual import work
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Label, ProgressBar

from frontend import api

STEPS = ["Loading vocabulary...", "Loading grammar...", "Loading user's data..."]


class StartupScreen(Screen):
    def compose(self):
        with Middle():
            with Center():
                yield Label("TOEFL Trainer", id="startup-title")
            with Center():
                yield ProgressBar(total=len(STEPS), show_eta=False,
                                  id="startup-bar")
            with Center():
                yield Label(f"0/{len(STEPS)} {STEPS[0]}", id="startup-step")

    def on_mount(self) -> None:
        self.boot()

    @work
    async def boot(self) -> None:
        label = self.query_one("#startup-step", Label)
        bar = self.query_one("#startup-bar", ProgressBar)
        health = None
        for _ in range(40):                 # wait for backend (~20s)
            try:
                health = await api.health()
                break
            except Exception:
                await asyncio.sleep(0.5)
        if health is None:
            label.update("[red]Backend not reachable — start it with "
                         "`python run.py`[/red]")
            return
        for i, step in enumerate(STEPS):
            label.update(f"{i}/{len(STEPS)} {step}")
            await asyncio.sleep(0.35)
            bar.advance(1)
        label.update(f"{len(STEPS)}/{len(STEPS)} Ready — "
                     f"{health['vocabulary']} words, "
                     f"{health['grammar_points']} grammar points")
        await asyncio.sleep(0.6)
        from frontend.screens.welcome import WelcomeScreen
        self.app.switch_screen(WelcomeScreen())

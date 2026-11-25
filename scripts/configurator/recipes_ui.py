"""Offline recipe explanations; opening a related stock browser is separate."""

from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static
from .recipes import RECIPES, matching_recipes


class RecipeBrowser(ModalScreen[str | None]):
    DEFAULT_CSS = """
    RecipeBrowser { align: center middle; }
    RecipeBrowser > VerticalScroll { width: 95%; max-width: 120; height: 95%;
      border: round $accent; padding: 1 2; background: $surface; }
    RecipeBrowser Static { margin-bottom: 1; }
    """
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self):
        super().__init__()
        self.updating = False
        self.choices = RECIPES

    def compose(self):
        with VerticalScroll():
            yield Static("Upstream gallery recipes · visual intent and ingredients", markup=False)
            yield Static(
                "Read-only, offline reference. These are not imported commands or certified event presets. Browsing preserves your draft and inactive choices.",
                markup=False,
            )
            yield Input(
                placeholder="Filter by title, body, setting or prerequisite", id="recipe-filter"
            )
            yield Static("", id="recipe-count", markup=False)
            yield Select(
                [(r.title, r.page) for r in RECIPES],
                value=RECIPES[0].page,
                allow_blank=True,
                id="recipe-selection",
            )
            yield Static("", id="recipe-details", markup=False)
            with Horizontal():
                yield Button("Browse related stock scene", id="recipe-stock", disabled=True)
                yield Button("Back", id="recipe-back")

    def on_mount(self):
        self.describe()

    def on_input_changed(self, event):
        if event.input.id != "recipe-filter":
            return
        selected = self.query_one("#recipe-selection", Select)
        old = selected.value
        self.choices = matching_recipes(event.value)
        self.updating = True
        try:
            selected.set_options([(r.title, r.page) for r in self.choices])
            selected.value = (
                old
                if any(r.page == old for r in self.choices)
                else self.choices[0].page
                if self.choices
                else Select.NULL
            )
        finally:
            self.updating = False
        self.describe()

    def selected_recipe(self):
        value = self.query_one("#recipe-selection", Select).value
        return next((r for r in self.choices if r.page == value), None)

    def on_select_changed(self, event):
        if event.select.id == "recipe-selection" and not self.updating:
            self.describe()

    def describe(self):
        recipe = self.selected_recipe()
        self.query_one("#recipe-count", Static).update(
            f"{len(self.choices)} shown / {len(RECIPES)} upstream examples"
        )
        self.query_one("#recipe-details", Static).update(
            recipe.describe()
            if recipe
            else "No matching recipes. Clear or revise the filter; no draft settings changed."
        )
        self.query_one("#recipe-stock", Button).disabled = recipe is None or recipe.stock is None

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == "recipe-back":
            self.action_back()
        elif event.button.id == "recipe-stock":
            recipe = self.selected_recipe()
            if recipe and recipe.stock:
                self.dismiss(recipe.stock)

    def action_back(self):
        self.dismiss(None)

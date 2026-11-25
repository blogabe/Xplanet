"""Recipe browsing never mutates drafts; stock opening uses the normal library."""

import unittest
from unittest.mock import patch
from textual.widgets import Input, Select, Button, Static
from configurator.recipes_ui import RecipeBrowser
from configurator.library_ui import SceneLibrary
from tests.configurator.ui import fixtures

click = fixtures.click


class RecipeUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.setup_editor

    async def test_filter_cancel_and_repeated_browse_preserve_invalid_draft_and_undo(self):
        async with self.app.run_test(size=(110, 50)) as pilot:
            self.app.query_one("#latitude", Input).value = "not-a-number"
            await pilot.pause()
            before = self.app.history.current
            with (
                patch.object(self.app, "open_url") as browser,
                patch("configurator.app.open_image") as viewer,
            ):
                for _ in range(2):
                    await click(pilot, "#recipes")
                    await pilot.pause()
                    self.assertIsInstance(self.app.screen, RecipeBrowser)
                    self.app.screen.query_one("#recipe-filter", Input).value = "SPICE kernels"
                    await pilot.pause()
                    self.assertIn(
                        "SPICE", str(self.app.screen.query_one("#recipe-details", Static).render())
                    )
                    self.app.screen.query_one("#recipe-filter", Input).value = "no-match-ever"
                    await pilot.pause()
                    self.assertTrue(self.app.screen.query_one("#recipe-stock", Button).disabled)
                    await pilot.press("escape")
                    await pilot.pause()
                browser.assert_not_called()
                viewer.assert_not_called()
            self.assertEqual(self.app.history.current, before)
            self.assertTrue(self.app.history.dirty)
            self.assertEqual(self.app.query_one("#latitude", Input).value, "not-a-number")
            await pilot.press("ctrl+z")
            await pilot.pause()
            self.assertNotEqual(self.app.query_one("#latitude", Input).value, "not-a-number")
        self.assertEqual(list((self.root / "config").iterdir()), [])
        self.assertFalse((self.root / ".state").exists())

    async def test_related_stock_is_separate_review_then_explicit_open(self):
        async with self.app.run_test(size=(110, 50)) as pilot:
            self.app.query_one("#latitude", Input).value = "23"
            await pilot.pause()
            renderer = self.app.query_one("#renderer", Input).value
            await click(pilot, "#recipes")
            self.app.screen.query_one("#recipe-filter", Input).value = "south america"
            await pilot.pause()
            await click(pilot, "#recipe-stock")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, SceneLibrary)
            self.assertEqual(
                self.app.screen.query_one("#library-filter", Input).value, "earth-solar-dawn"
            )
            self.assertTrue(self.app.screen.dirty)
            self.assertEqual(self.app.draft().latitude, 23)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(self.app.draft().latitude, 23)
            await click(pilot, "#recipes")
            self.app.screen.query_one("#recipe-filter", Input).value = "south america"
            await pilot.pause()
            await click(pilot, "#recipe-stock")
            await pilot.pause()
            await click(pilot, "#library-open")
            await pilot.pause()
            self.assertEqual(self.app.document.source.name, "earth-solar-dawn.conf")
            self.assertEqual(self.app.query_one("#renderer", Input).value, renderer)
            self.assertFalse(self.app.history.dirty)
        self.assertEqual(list((self.root / "config").iterdir()), [])

    async def test_reference_only_and_active_work_cannot_open_stock(self):
        async with self.app.run_test(size=(110, 50)) as pilot:
            before = self.app.history.current
            await click(pilot, "#recipes")
            self.app.screen.query_one("#recipe-filter", Input).value = "Triton"
            await pilot.pause()
            self.assertTrue(self.app.screen.query_one("#recipe-stock", Button).disabled)
            await pilot.press("escape")
            await pilot.pause()
            with patch.object(self.workspace, "busy", True):
                self.app.browse_recipe_stock("earth-solar-dawn")
            self.assertNotIsInstance(self.app.screen, SceneLibrary)
            self.assertEqual(self.app.history.current, before)

    async def test_help_and_exit_do_not_discard_underlying_draft(self):
        async with self.app.run_test(size=(110, 50)) as pilot:
            self.app.query_one("#latitude", Input).value = "23"
            await pilot.pause()
            await click(pilot, "#recipes")
            recipe = self.app.screen
            await pilot.press("f1")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(self.app.screen, recipe)
            await pilot.press("ctrl+d")
            await pilot.pause()
            self.assertFalse(self.app.leaving)
            await click(pilot, "#keep-editing")
            await pilot.pause()
            self.assertIs(self.app.screen, recipe)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(self.app.draft().latitude, 23)

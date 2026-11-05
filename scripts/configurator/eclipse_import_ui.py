"""Explicit local data import: no browser, provider request or desktop action."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Label,Static

class EclipseImport(ModalScreen[tuple|None]):
    DEFAULT_CSS="""
    EclipseImport { align: center middle; }
    EclipseImport > VerticalScroll { width: 90%; max-width: 110; height: auto; max-height: 90%; border: round $accent; padding: 1 2; background: $surface; }
    """
    BINDINGS=[('escape','back','Back')]
    def compose(self):
        with VerticalScroll():
            yield Static('Import an explicit LOCAL NASA-format central-path table')
            yield Static('Format, event identity and coverage are validated. A hash/reference agreement does NOT prove NASA authorship or a live download. No provider facts are invented; no source file is modified.')
            yield Label('Absolute local HTML/text file, at most 2 MiB')
            yield Input('',id='eclipse-local-file')
            yield Label('Official event reference URL — identity only, NEVER fetched')
            yield Input('',id='eclipse-reference-url')
            yield Label('First timed row UTC date — required for midnight crossings (YYYY-MM-DD)')
            yield Input('',id='eclipse-first-row-date')
            yield Static('The event title alone does not establish which UTC day contains the first row. Supply this date from independent evidence; it remains user-supplied, unverified provenance.')
            yield Static('Only a validated derived path and minimal provenance are retained, not your local pathname or raw HTML. Review the imported coverage, then choose Fixed UTC; Now stays inactive.')
            with Horizontal():
                yield Button('Import local prediction',id='eclipse-import-confirm',variant='primary')
                yield Button('Back',id='eclipse-import-back')
    def on_button_pressed(self,event):
        event.stop();self.dismiss((self.query_one('#eclipse-local-file',Input).value,self.query_one('#eclipse-reference-url',Input).value,self.query_one('#eclipse-first-row-date',Input).value or None) if event.button.id=='eclipse-import-confirm' else None)
    def action_back(self):self.dismiss(None)

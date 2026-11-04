"""Read-only bundled help; no browser, renderer or configuration operations."""
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Markdown,Static
from .guide import read_guide
from .resources import safe

class StudioHelp(ModalScreen):
    DEFAULT_CSS='''
    StudioHelp { align: center middle; }
    StudioHelp > VerticalScroll { width: 95%; max-width: 120; height: 95%; border: round $accent; padding: 1 2; background: $surface; }
    StudioHelp Markdown { background: $surface; }
    '''
    BINDINGS=[('escape','back','Back')]
    def compose(self):
        with VerticalScroll(id='studio-help-scroll'):
            yield Static('Scene studio help · F1 / Escape returns · scroll to read')
            try:text=read_guide()
            except (OSError,ValueError,UnicodeError) as exc:text='# Help unavailable\n\n'+safe(exc)+'\n\nRestore docs/configurator-user-guide.md from the complete checkout. No state changed.'
            yield Markdown(text,id='studio-help-text',open_links=False)
            yield Static('Related links name files in docs; help does not launch a browser. CLI: scripts/xplanet.sh config --guide',id='studio-help-link',markup=False)
            yield Button('Back to previous screen',id='studio-help-back')
    def on_markdown_link_clicked(self,event):
        event.stop();self.query_one('#studio-help-link',Static).update('Reference: '+safe(event.href)+' — read it in the checkout; no browser opened.')
    def on_button_pressed(self,event):
        if event.button.id=='studio-help-back':event.stop();self.action_back()
    def action_back(self):self.dismiss()

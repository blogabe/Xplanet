"""Explicit destination and confirmation for durable copies, not scene saves."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Static

class RenderExport(ModalScreen[str|None]):
    DEFAULT_CSS="""
    RenderExport { align: center middle; }
    RenderExport > VerticalScroll { width: 85; max-width: 95%; height: auto; max-height: 90%; border: round $accent; padding: 1 2; background: $surface; }
    """
    BINDINGS=[('escape','back','Back')]
    def __init__(self,kind,description,destination):super().__init__();self.kind,self.description,self.destination=kind,description,destination
    def compose(self):
        with VerticalScroll():
            yield Static('Export retained '+('preview' if self.kind=='preview' else 'comparison sheet')+' as a durable copy?')
            yield Static(self.description,markup=False)
            yield Static('Exports the recorded snapshot, which may differ from the current draft. No rerender, provider, scene save, selection or desktop operation. Image bytes and embedded metadata are retained; review before sharing.')
            yield Static('Choose a NEW directory. The default output/exports parents are created only when you confirm; other parents must already exist. Existing destinations and symlink paths are refused; nothing is overwritten. A preview exports preview.png plus export.json; a comparison sheet exports its three PNGs, static HTML and manifests.')
            yield Input(self.destination,id='render-export-directory')
            with Horizontal():
                yield Button('Export copy',id='render-export-confirm',variant='primary')
                yield Button('Back',id='render-export-back')
    def on_button_pressed(self,event):
        event.stop();self.dismiss(self.query_one('#render-export-directory',Input).value if event.button.id=='render-export-confirm' else None)
    def action_back(self):self.dismiss(None)

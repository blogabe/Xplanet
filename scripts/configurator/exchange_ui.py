"""Explicit saved-file exchange forms; no filesystem work on opening/cancel."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Label,Static


class SceneExchange(ModalScreen[tuple|None]):
    DEFAULT_CSS="""
    SceneExchange { align: center middle; }
    SceneExchange > VerticalScroll { width: 94%; max-width: 110; height: auto;
      max-height: 90%; border: round $accent; padding: 1 2; background: $surface; }
    SceneExchange Static { margin-bottom: 1; }
    """
    BINDINGS=[('escape','back','Back')]

    def __init__(self,mode,source='',renderer='',dirty=False):
        super().__init__();self.mode,self.source,self.renderer,self.dirty=mode,source,renderer,dirty

    def compose(self):
        with VerticalScroll():
            yield Static('Export a SAVED scene as an archive' if self.mode=='export' else 'Import an archive as a NEW scene copy')
            if self.mode=='export':
                yield Static('Reads the saved native files below again at confirmation. Unsaved editor changes are not included; Save a new scene first if you want to share them.')
                if self.dirty:yield Static('This editor has unsaved changes. Export does not save or replace that draft.')
                yield Label('Saved .conf/.def path or legacy scene directory')
            else:
                yield Static('Untrusted archive validation happens before creating the destination. No execution, selection, restart or overwrite. The imported copy uses xp.conf/xp.def in a new directory.')
                yield Static('Local renderer reference (validated, never executed): '+self.renderer,markup=False)
                yield Label('Scene archive path')
            yield Input(self.source,id='exchange-source')
            yield Label('NEW destination directory in an existing real parent — absolute path')
            yield Input('',id='exchange-destination')
            if self.mode=='export':
                yield Label('Optional illustrative PNG path — leave blank to omit')
                yield Input('',id='exchange-preview')
                yield Static('No current preview is attached automatically. The selected PNG is an illustration, not verified to match the saved scene. Metadata is stripped; personal labels/pixels remain. Review before sharing.')
            else:
                yield Static('Import preserves the current draft. After success you may choose Open separately; replacing a dirty draft still requires explicit confirmation.')
            yield Static('Bundled maps stay references. Exchange v1 refuses all retained provider captures, including disabled ones. Hashes verify consistency, not authenticity; review user-authored annotations before sharing.')
            yield Static('',id='exchange-message',markup=False)
            with Horizontal():
                yield Button('Create archive copy' if self.mode=='export' else 'Import as new copy',id='exchange-confirm',variant='primary')
                yield Button('Back',id='exchange-back')

    def on_button_pressed(self,event):
        event.stop()
        if event.button.id=='exchange-back':self.action_back();return
        if event.button.id!='exchange-confirm':return
        source=self.query_one('#exchange-source',Input).value;destination=self.query_one('#exchange-destination',Input).value
        preview=self.query_one('#exchange-preview',Input).value if self.mode=='export' else ''
        if not source.strip() or not destination.strip():
            self.query_one('#exchange-message',Static).update('Choose both a source and a new destination. Nothing has been written.');return
        self.dismiss((source,destination,preview if preview.strip() else None))

    def action_back(self):self.dismiss(None)

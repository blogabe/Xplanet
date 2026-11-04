"""Read-only scene browsing; validate one selected pair, never preload captures."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Select,Static
from .library import list_scenes
from .workspace import open_view
from .resources import safe

class SceneLibrary(ModalScreen[str|None]):
    DEFAULT_CSS="""
    SceneLibrary { align: center middle; }
    SceneLibrary > VerticalScroll { width: 90%; max-width: 110; height: 90%;
      border: round $accent; padding: 1 2; background: $surface; }
    SceneLibrary Static { margin-bottom: 1; }
    """
    BINDINGS=[('escape','back','Back')]

    def __init__(self,library,dirty=False,stock=False):
        super().__init__();self.library,self.dirty,self.stock=library,dirty,stock;self.updating=False
        try:self.all_choices=list_scenes(library);self.error=None
        except (ValueError,OSError) as exc:self.all_choices=[];self.error=str(exc)
        self.choices=list(self.all_choices)
        self.inspected=None;self.inspection_text='';self.inspection_valid=False

    def compose(self):
        with VerticalScroll():
            yield Static(('Stock scenes: ' if self.stock else 'Saved scenes: ')+str(self.library),markup=False)
            yield Static('Open a snapshot, experiment, and save a new copy. Browsing never renames, deletes or activates a scene.')
            if self.dirty:yield Static('Opening a valid pair replaces unsaved editor changes. Source files remain unchanged.')
            yield Input('',placeholder='Filter scene names',id='library-filter')
            yield Static('',id='library-count',markup=False)
            yield Select([(p.stem,str(p)) for p in self.choices],allow_blank=True,value=str(self.choices[0]) if self.choices else Select.NULL,id='library-selection')
            yield Static('',id='library-summary',markup=False)
            with Horizontal():
                yield Button('Open selected',id='library-open',disabled=True)
                yield Button('Back',id='library-back')

    def on_mount(self):self.describe()

    def on_input_changed(self,event):
        if event.input.id!='library-filter':return
        selected=self.query_one('#library-selection',Select);value=selected.value;needle=event.value.casefold()
        self.choices=[path for path in self.all_choices if needle in path.stem.casefold()]
        self.updating=True
        try:
            selected.set_options([(path.stem,str(path)) for path in self.choices])
            selected.value=value if any(str(path)==value for path in self.choices) else str(self.choices[0]) if self.choices else Select.NULL
        finally:self.updating=False
        self.describe()

    def on_select_changed(self,event):
        if event.select.id=='library-selection' and not self.updating:self.describe()

    def describe(self):
        self.query_one('#library-open',Button).disabled=True
        self.query_one('#library-count',Static).update(f'{len(self.choices)} shown / {len(self.all_choices)} named pairs. Only the selected pair is inspected.')
        value=self.query_one('#library-selection',Select).value
        if value is Select.NULL:
            message=self.error or ('No names match this filter.' if self.all_choices else 'No named pairs. Save a new scene, or restore missing stock files. Nothing was created.')
            self.query_one('#library-summary',Static).update(safe(message));return
        # A name-filter keystroke must not reread a large frozen capture when
        # the selected path did not change. This is one inspected snapshot only;
        # Open always revalidates, including any changes since inspection.
        if str(value)!=self.inspected:
            self.inspected=str(value);self.inspection_valid=False
            try:
                document=open_view(str(value));view=document.view
                message=view.summary()+'\n'+f'Preview: {view.geometry}; native files: {len(document.native_files)}. Saved renderer/root are references only; the editor keeps its local renderer.'
                if document.capture or document.observations:message+='\nContains frozen observational data; scene time does not refresh it.'
                message+='\nInspected snapshot; Open revalidates the pair. No render, provider request, desktop selection or file change occurs.'
                self.inspection_text=safe(message);self.inspection_valid=True
            except (OSError,ValueError) as exc:self.inspection_text='Cannot open this pair: '+safe(exc)+'\nKeep the originals. Use Inspect native files for unsupported content; no repair or conversion was attempted. Reopen the browser to inspect updated files.'
        self.query_one('#library-summary',Static).update(self.inspection_text)
        self.query_one('#library-open',Button).disabled=not self.inspection_valid

    def on_button_pressed(self,event):
        if event.button.id=='library-open' and not event.button.disabled:
            value=self.query_one('#library-selection',Select).value
            if value is not Select.NULL:self.dismiss(str(value))
        elif event.button.id=='library-back':self.action_back()
    def action_back(self):self.dismiss(None)

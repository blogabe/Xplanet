"""In-memory per-moon editor; only explicit valid results reach the main draft."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Select,Static
from .model import SYSTEMS,parse_moon_scales,encode_moon_scales,moon_scale_number,number


class MoonScalesScreen(ModalScreen[str|None]):
    BINDINGS=[('escape','cancel','Cancel edits')]
    DEFAULT_CSS='''
    MoonScalesScreen { align: center middle; }
    MoonScalesScreen > VerticalScroll {
      width: 90%; max-width: 100; height: auto; max-height: 90%;
      border: round $accent; padding: 1 2; background: $surface;
    }
    MoonScalesScreen Static { margin-bottom: 1; }
    '''

    def __init__(self,target,shared,original):
        super().__init__();self.members=SYSTEMS[target];self.shared=moon_scale_number(shared)
        self.original=original;self.initial=parse_moon_scales(original)
        self.edits={body:number(value) for body,value in self.initial.items()}
        for body in self.members:self.edits.setdefault(body,'')
        self.current=self.members[0];self.ready=False

    def compose(self):
        with VerticalScroll():
            yield Static('Individual moon scales — draft only')
            yield Static(f'An override REPLACES the shared {number(self.shared)}× scale. Blank uses shared; 1 keeps the engine\'s natural size. Zero does not hide a body. No preview, source save or Apply occurs here.')
            yield Select([(body.title(),body) for body in self.members],value=self.current,allow_blank=False,id='scale-moon')
            yield Input('',placeholder='Blank = shared scale',id='moon-override-value')
            yield Static('',id='moon-override-summary',markup=False)
            yield Static('',id='moon-override-error',markup=False)
            with Horizontal():
                yield Button('Use overrides in draft',id='moon-override-use',variant='primary')
                yield Button('Cancel edits',id='moon-override-cancel')

    def on_mount(self):
        self.show_selected();self.ready=True;self.summarize()

    def remember(self):self.edits[self.current]=self.query_one('#moon-override-value',Input).value

    def show_selected(self):
        widget=self.query_one('#moon-override-value',Input)
        with widget.prevent(Input.Changed):widget.value=self.edits[self.current]

    def summarize(self):
        lines=[]
        for body in self.members:
            value=self.edits[body]
            try:scale=number(moon_scale_number(value)) if value else number(self.shared)
            except ValueError:scale='invalid'
            lines.append(body.title()+': '+scale+'× ('+('override' if value else 'shared')+')')
        other=sum(body not in self.members for body in self.initial)
        if other:lines.append(f'{other} other-family override(s) retained unchanged.')
        self.query_one('#moon-override-summary',Static).update('\n'.join(lines))

    def on_select_changed(self,event):
        if self.ready and event.select.id=='scale-moon':
            self.remember();self.current=str(event.value);self.show_selected();self.summarize()

    def on_input_changed(self,event):
        if self.ready and event.input.id=='moon-override-value':
            self.remember();self.summarize();self.query_one('#moon-override-error',Static).update('')

    def on_button_pressed(self,event):
        if event.button.id=='moon-override-cancel':self.dismiss(None)
        elif event.button.id=='moon-override-use':
            self.remember()
            try:
                result=encode_moon_scales(self.edits)
                self.dismiss(self.original if parse_moon_scales(result)==self.initial else result)
            except ValueError as exc:self.query_one('#moon-override-error',Static).update(str(exc))

    def action_cancel(self):self.dismiss(None)

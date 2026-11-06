"""Separate native literal-copy UI; never loads opaque content into scene preview."""
import asyncio
from pathlib import Path
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Label,Select,Static
from .native_patch import FIELDS
from .fileio import native_error
from .native_inspection import display

CSS='''
NativePatchPath, NativePatchScreen { align: center middle; }
NativePatchPath > VerticalScroll, NativePatchScreen > VerticalScroll {
 width: 90%; max-width: 100; height: auto; max-height: 90%;
 border: round $accent; padding: 1 2; background: $surface;
}
NativePatchScreen Static { margin-bottom: 1; }
'''


class NativePatchPath(ModalScreen[str|None]):
    DEFAULT_CSS=CSS
    BINDINGS=[('escape','cancel','Back')]

    def __init__(self,initial):super().__init__();self.initial=initial

    def compose(self):
        with VerticalScroll():
            yield Static('Native literal values — copy-on-write, not scene conversion')
            yield Static('Choose a .conf file. Definitions/scripts/assets are not opened or executed. Source and current scene draft remain unchanged.')
            yield Input(self.initial,id='native-patch-source')
            with Horizontal():
                yield Button('Open safe values',id='native-patch-open',variant='primary')
                yield Button('Back',id='native-patch-back')

    def on_button_pressed(self,event):self.dismiss(self.query_one('#native-patch-source',Input).value if event.button.id=='native-patch-open' else None)
    def action_cancel(self):self.dismiss(None)


class NativePatchScreen(ModalScreen[Path|None]):
    DEFAULT_CSS=CSS
    BINDINGS=[('escape','cancel','Back')]

    def __init__(self,document):
        super().__init__();self.document=document;self.edits=document.initial_values();self.current=document.sections[0]
        self.ready=False;self.proposal=None;self.reviewed_destination=None;self.busy=False

    def compose(self):
        with VerticalScroll():
            yield Static('Native literal copy: '+display(str(self.document.source)),markup=False)
            yield Static('Edit only the supported literal values below. Other bytes, comments, repeated file entries and assets stay unchanged. This does not load an arbitrary scene or execute its definitions.')
            yield Select([('['+section+']',section) for section in self.document.sections],value=self.current,allow_blank=False,id='native-section')
            yield Static('Only unique supported sections are listed. Blank leaves the original unchanged; an absent setting becomes an explicit override only if entered. Inherited/effective values are not inferred.')
            for key,(_,_,context) in FIELDS.items():
                yield Label(key+' — '+context)
                yield Input('',id='native-value-'+key)
                yield Static('',id='native-context-'+key,markup=False)
            yield Label('NEW .conf in the same directory (no companion .def is written)')
            yield Input(str(self.document.source.with_name(self.document.source.stem+'-edited.conf')),id='native-patch-destination')
            yield Static('The copy relies on the same assets, working directory and search paths as the original. It is not a generated studio scene and cannot use the studio preview. No file is activated; original source/scripts stay untouched.')
            yield Static('',id='native-patch-review',markup=False)
            yield Static('',id='native-patch-status',markup=False)
            with Horizontal():
                yield Button('Review copy',id='native-patch-review-button',variant='primary')
                yield Button('Confirm copy',id='native-patch-confirm',variant='warning')
                yield Button('Cancel',id='native-patch-cancel')

    def on_mount(self):
        self.show_section();self.ready=True;self.invalidate_review()

    def show_section(self):
        for key in FIELDS:
            slot=next(s for s in self.document.slots if s.section==self.current and s.key==key)
            widget=self.query_one('#native-value-'+key,Input)
            with widget.prevent(Input.Changed):widget.value=self.edits[self.current][key]
            widget.disabled=bool(slot.reason)
            self.query_one('#native-context-'+key,Static).update(slot.reason or ('Existing literal: '+slot.literal if slot.literal else 'Not explicitly set here; entering a value adds an override.'))

    def remember(self):
        for key in FIELDS:self.edits[self.current][key]=self.query_one('#native-value-'+key,Input).value

    def invalidate_review(self):
        had_review=self.proposal is not None
        self.proposal=None;self.reviewed_destination=None
        self.query_one('#native-patch-confirm').display=False
        self.query_one('#native-patch-review',Static).update('')
        if had_review:self.query_one('#native-patch-status',Static).update('Values or destination changed; review the copy again.')

    def on_select_changed(self,event):
        if self.ready and event.select.id=='native-section':
            self.remember();self.current=str(event.value);self.show_section();self.invalidate_review()

    def on_input_changed(self,event):
        if self.ready:
            self.remember();self.invalidate_review()

    def on_button_pressed(self,event):
        if self.busy:return
        action=event.button.id
        if action=='native-patch-cancel':self.dismiss(None);return
        try:
            self.remember()
            if action=='native-patch-review-button':
                self.invalidate_review()
                self.proposal=self.document.prepare(self.edits)
                self.reviewed_destination=self.query_one('#native-patch-destination',Input).value
                summary='\n'.join(self.proposal.changes) if self.proposal.changes else 'No value changes: exact original bytes will be copied, including literal spelling and line endings.'
                self.query_one('#native-patch-review',Static).update(summary+'\n\n'+'\n'.join(self.document.review(self.proposal))+'\nDestination: '+display(self.reviewed_destination)+'\nOriginal .conf/.def and assets will not be overwritten or moved.')
                self.query_one('#native-patch-confirm').display=True
                self.query_one('#native-patch-status',Static).update('Review these changes, then confirm the new file.')
            elif action=='native-patch-confirm':
                destination=self.query_one('#native-patch-destination',Input).value
                current=self.document.prepare(self.edits)
                if self.proposal is None or current.data!=self.proposal.data or destination!=self.reviewed_destination:
                    self.invalidate_review();raise ValueError('Values or destination changed; review the copy again.')
                self.busy=True
                self.query_one(VerticalScroll).disabled=True
                self.run_worker(self.save_copy(destination,self.proposal))
        except (ValueError,OSError) as exc:
            self.query_one('#native-patch-status',Static).update(native_error(exc))

    async def save_copy(self,destination,proposal):
        try:
            result=await self.app.workspace.file_operation(self.document.save_copy,destination,proposal)
            await self.app.exit_decision.wait()
            if not self.app.leaving:self.dismiss(result)
        except asyncio.CancelledError:
            self.query_one('#native-patch-status',Static).update('Copy cancelled. Source retained; inspect the new destination before retrying.')
        except (ValueError,OSError) as exc:self.query_one('#native-patch-status',Static).update(native_error(exc))
        finally:
            self.busy=False
            if self.is_mounted:self.query_one(VerticalScroll).disabled=False

    def action_cancel(self):
        if self.busy:self.app.run_worker(self.app.workspace.stop())
        else:self.dismiss(None)

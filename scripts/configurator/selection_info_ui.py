"""On-demand selected-scene clarity; no automatic import or lifecycle operation."""
import asyncio
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Static
from .selection_info import inspect_selected
from .resources import safe
from .fileio import native_error


class SelectedSceneScreen(ModalScreen):
    DEFAULT_CSS='''
    SelectedSceneScreen { align: center middle; }
    SelectedSceneScreen > VerticalScroll { width: 90%; max-width: 110; height: 90%;
      border: round $accent; padding: 1 2; background: $surface; }
    SelectedSceneScreen Static { margin-bottom: 1; }
    '''
    BINDINGS=[('escape','back','Back')]

    def __init__(self,root,dirty=False):super().__init__();self.root=root;self.dirty=dirty;self.info=None;self.busy=False;self.closing=False

    def compose(self):
        with VerticalScroll():
            yield Static('Selected desktop scene — next start/restart')
            yield Static('This is read-only inspection. It does not discover the running scene, restart, refresh data or change selection.')
            if self.dirty:yield Static('Opening a native draft replaces unsaved editor changes only after you explicitly choose Open.')
            yield Static('',id='selected-scene-info',markup=False)
            with Horizontal():
                yield Button('Refresh inspection',id='selected-scene-refresh')
                yield Button('Open native draft / replace unsaved draft' if self.dirty else 'Open native scene as draft',id='selected-scene-open',disabled=True)
                yield Button('Back',id='selected-scene-back')

    def on_mount(self):self.refresh_info()

    def refresh_info(self):
        if not self.busy:
            self.busy=True;self.run_worker(self.inspect_info())

    async def inspect_info(self,opening=False):
        self.busy=True
        self.query_one('#selected-scene-open',Button).disabled=True
        self.query_one('#selected-scene-refresh',Button).disabled=True
        try:
            info=await self.app.workspace.file_operation(inspect_selected,self.root)
            if self.closing:return
            if opening:
                if self.info is None or info.selection!=self.info.selection or info.record!=self.info.record:raise ValueError('Selection changed; refresh before opening.')
                await self.app.exit_decision.wait()
                if not self.app.leaving:self.dismiss(str(info.native_path))
            else:
                self.info=info
                self.query_one('#selected-scene-info',Static).update('\n\n'.join(safe(part) for part in info.sections()))
                self.query_one('#selected-scene-open',Button).disabled=info.native_path is None
        except asyncio.CancelledError:
            if not self.closing:self.query_one('#selected-scene-info',Static).update('Inspection cancelled. Refresh to inspect current state; files and draft unchanged.')
        except (OSError,ValueError) as exc:
            self.info=None
            self.query_one('#selected-scene-info',Static).update(('Cannot open this reviewed snapshot: ' if opening else 'Selection unavailable or invalid: ')+safe(native_error(exc))+'\nNo custom configuration fallback was assumed; files and draft remain unchanged.')
        finally:
            self.busy=False
            if self.is_mounted:self.query_one('#selected-scene-refresh',Button).disabled=False

    def on_button_pressed(self,event):
        event.stop()
        if event.button.id=='selected-scene-back':self.action_back()
        elif event.button.id=='selected-scene-refresh':self.refresh_info()
        elif event.button.id=='selected-scene-open' and self.info and self.info.native_path and not self.busy:
            self.busy=True;self.run_worker(self.inspect_info(opening=True))

    def action_back(self):
        if self.closing:return
        self.closing=True
        self.run_worker(self.close_inspection())

    async def close_inspection(self):
        await self.app.workspace.stop()
        self.dismiss(None)

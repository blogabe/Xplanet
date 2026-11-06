"""Explicit recovery inspection; data snapshots never replay executable actions."""
import asyncio
from datetime import datetime,timezone
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Select,Static,Checkbox
from .resources import safe
from .fileio import native_error

class RecoveryScreen(ModalScreen):
    DEFAULT_CSS='''
    RecoveryScreen { align: center middle; }
    RecoveryScreen > VerticalScroll { width: 90%; max-width: 110; height: 90%; border: round $accent; padding: 1 2; background: $surface; }
    RecoveryScreen Static { margin-bottom: 1; }
    '''
    BINDINGS=[('escape','back','Back')]
    def __init__(self,store):
        super().__init__();self.busy=False;self.store=store;self.loaded=None;self.discard_ready=None
        self.closing=False
        self.rows=[];self.error='Reading private recovery sessions…'
    def compose(self):
        with VerticalScroll(id="recovery-content"):
            yield Static('Private recovery drafts — not native saves or desktop selection')
            yield Static('Recover copies raw draft text and frozen captures into this editor only. It never runs a renderer, source script, provider or selection operation. Sources are not reread. No undo stack or preview images are restored.')
            options=[]
            for row in self.rows:
                stamp=datetime.fromtimestamp(row['at'],timezone.utc).strftime('%Y-%m-%d %H:%MZ') if row['at'] is not None else 'unknown time'
                options.append((stamp+' · '+row['id'][:8]+(' [active]' if row['active'] else '')+(' [unreadable]' if row['error'] else ''),row['id']))
            yield Select(options,allow_blank=True,value=options[0][1] if options else Select.NULL,id='recovery-selection')
            yield Static(safe(self.error) or ('Choose Inspect to verify all referenced bytes before recovery. Active drafts stay with their existing editor.' if options else 'No recoverable sessions. Nothing was created.'),id='recovery-details',markup=False)
            yield Checkbox('Restore the recorded executable as proposed text (off: retain local choice)',value=False,id='recovery-renderer')
            with Horizontal():
                yield Button('Inspect checkpoint',id='recovery-inspect',disabled=not bool(options))
                yield Button('Recover inspected draft',id='recovery-recover',disabled=True)
                yield Button('Discard inspected session…',id='recovery-discard',disabled=True)
                yield Button('Back',id='recovery-back')
    def on_mount(self):
        self.busy=True
        self.run_worker(self.load_entries())

    async def load_entries(self):
        try:
            self.rows=await self.app.workspace.file_operation(self.store.entries)
            if self.closing:return
            options=[]
            for row in self.rows:
                stamp=datetime.fromtimestamp(row['at'],timezone.utc).strftime('%Y-%m-%d %H:%MZ') if row['at'] is not None else 'unknown time'
                options.append((stamp+' · '+row['id'][:8]+(' [active]' if row['active'] else '')+(' [unreadable]' if row['error'] else ''),row['id']))
            selection=self.query_one('#recovery-selection',Select)
            selection.set_options(options);selection.value=options[0][1] if options else Select.NULL
            self.query_one('#recovery-inspect',Button).disabled=not bool(options)
            self.query_one('#recovery-details',Static).update('Choose Inspect to verify all referenced bytes before recovery. Active drafts stay with their existing editor.' if options else 'No recoverable sessions. Nothing was created.')
        except asyncio.CancelledError:self.query_one('#recovery-details',Static).update('Recovery inspection cancelled. Reopen this browser to retry.')
        except (OSError,ValueError) as exc:self.query_one('#recovery-details',Static).update(native_error(exc))
        finally:self.busy=False

    def reset_review(self):
        self.loaded=None;self.discard_ready=None
        self.query_one('#recovery-recover',Button).disabled=True;self.query_one('#recovery-discard',Button).disabled=True
        self.query_one('#recovery-discard',Button).label='Discard inspected session…'
    def on_select_changed(self,event):
        if event.select.id=='recovery-selection':
            self.reset_review();self.query_one('#recovery-details',Static).update('Inspect the selected checkpoint. No files changed.')
    def on_button_pressed(self,event):
        event.stop()
        value=self.query_one('#recovery-selection',Select).value;action=event.button.id
        if action=='recovery-back':self.action_back();return
        if value is Select.NULL or self.busy:return
        self.busy=True;self.query_one('#recovery-content').disabled=True
        self.run_worker(self.perform_action(action,value))

    async def perform_action(self,action,value):
        io=self.app.workspace.file_operation
        try:
            if action=='recovery-inspect':
                self.reset_review();self.loaded=await io(self.store.load,str(value))
                if self.closing:return
                r=self.loaded.record
                text='Inspected checkpoint: '+datetime.fromtimestamp(r['at'],timezone.utc).isoformat(timespec='seconds')+'\n'+('Previous complete checkpoint used because the latest is invalid.\n' if self.loaded.fallback else '')+'Source hint only (not reread): '+r['source']+'\nRaw fields include invalid text and retained inactive choices. Proposed executable text: '+r['current']['renderer'][:200]+(' … [display truncated; raw field retained]' if len(r['current']['renderer'])>200 else '')+'\nLocal executable choice is retained unless you explicitly select the checkbox. Recover never executes it; Preview stays explicit and validated.\nFrozen captures: '+str(len(self.loaded.clouds))+' clouds, '+str(len(self.loaded.observations))+' observational sets.\nFields changed from baseline: '+', '.join(key for key in r['current'] if r['current'][key]!=r['baseline'][key])
                text+='\nCurrent unsaved editor changes will be replaced only if you choose Recover. The original recovery session remains until explicitly discarded.'
                self.query_one('#recovery-details',Static).update(safe(text));self.query_one('#recovery-recover',Button).disabled=False
                self.query_one('#recovery-discard',Button).disabled=False
            elif action=='recovery-recover' and self.loaded is not None:
                # Revalidate after review; recovery may not adopt changed data.
                current=await io(self.store.load,str(value))
                if self.closing:return
                if current.revision!=self.loaded.revision:raise ValueError('Checkpoint changed since inspection; inspect again.')
                await self.app.exit_decision.wait()
                if not self.app.leaving:self.dismiss((current,self.query_one('#recovery-renderer',Checkbox).value))
            elif action=='recovery-discard' and self.loaded is not None:
                if self.discard_ready!=str(value):
                    self.discard_ready=str(value);self.query_one('#recovery-discard',Button).label='Confirm discard this session'
                    self.query_one('#recovery-details',Static).update('Confirm removes only this verified recovery session. Native files, other recovery sessions, selected scene and desktop remain unchanged. Back cancels.')
                else:
                    await io(self.store.discard,str(value));self.reset_review();self.query_one('#recovery-inspect',Button).disabled=True
                    self.query_one('#recovery-details',Static).update('Recovery session discarded. Reopen this browser to refresh the list.')
        except asyncio.CancelledError:
            self.reset_review();self.query_one('#recovery-details',Static).update('Recovery operation cancelled. Inspect the session again before retrying.')
        except (OSError,ValueError,TypeError,KeyError) as exc:
            self.reset_review();self.query_one('#recovery-details',Static).update('Recovery unavailable: '+safe(exc)+' Files were not repaired or replaced.')
        finally:
            self.busy=False;self.query_one('#recovery-content').disabled=False

    def action_back(self):
        if self.closing:return
        self.closing=True
        self.run_worker(self.close_browser())

    async def close_browser(self):
        await self.app.workspace.stop()
        self.dismiss(None)

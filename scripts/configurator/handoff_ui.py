"""Review/export and explicit scene-reference changes; no lifecycle operations."""
from pathlib import Path
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Input,Label,Static
from .handoff import create_plan,stage_plan,check_bundle
from .native_inspection import display
from .selection import inspect_selection,apply_bundle,restore_selection,read_revision,UncertainSelection


class HandoffScreen(ModalScreen[tuple]):
    DEFAULT_CSS='''
    HandoffScreen { align: center middle; }
    HandoffScreen > VerticalScroll { width: 90%; max-width: 110; height: auto;
      max-height: 90%; border: round $accent; padding: 1 2; background: $surface; }
    HandoffScreen Static { margin-bottom: 1; }
    '''
    BINDINGS=[('escape','cancel','Back')]

    def __init__(self,root,source,renderer,dirty=False,on_selection=None):
        super().__init__();self.root=Path(root);self.source=source;self.renderer=renderer
        self.dirty=dirty;self.plan=None;self.reviewed_inputs=None;self.ready=False;self.result=None
        self.selection_expected=None;self.selection_record=None;self.restore_pending=False
        self.receipt=None;self.selection_label=None;self.on_selection=on_selection

    def compose(self):
        with VerticalScroll():
            yield Static('Scene handoff — review and explicit selection')
            yield Static('Export a SAVED named scene from this checkout. This does not export the current editor draft, select a desktop scene, run setup, start Xplanet or change schedules.')
            if self.dirty:yield Static('The editor has unsaved changes. Save a new named scene first if you want those changes included; this dialog leaves the draft intact.')
            yield Label('Saved scene: absolute config/scenes/NAME.conf')
            yield Input(str(self.source or ''),id='handoff-source')
            yield Label('Explicit local renderer (saved foreign executable choices are not adopted)')
            yield Input(self.renderer,id='handoff-renderer')
            yield Label('Intended desktop WIDTHxHEIGHT — review the actual aspect ratio')
            yield Input('',placeholder='For example: 1920x1080',id='handoff-geometry')
            yield Label('NEW export directory, or existing bundle directory to check')
            yield Input(str(self.root/'config/handoff-review'),id='handoff-destination')
            yield Static('Resource limits: selected assets are hash-bound references, not copied. Stock textures, incidental-body textures, fonts and compiled resources are not fully bound. These checks do not certify rendering, desktop capability or astronomical accuracy. No network or provider refresh occurs.')
            yield Static('Apply selects an immutable revision for the NEXT explicit start/restart. It does not change the running desktop, legacy files or producer schedules. With no selector the legacy path remains the default. Invalid selections fail clearly; no silent legacy fallback.')
            yield Static('Bundles contain local paths and possibly frozen observation metadata. Review before sharing. Legacy xp.def/xp.conf are hashed, never executed or included as content.')
            yield Static('',id='handoff-review',markup=False)
            yield Static('',id='handoff-status',markup=False)
            with Horizontal():
                yield Button('Review export',id='handoff-review-button',variant='primary')
                yield Button('Confirm new export',id='handoff-confirm',variant='warning')
            with Horizontal():
                yield Button('Check existing bundle',id='handoff-check')
                yield Button('Back',id='handoff-back')
            with Horizontal():
                yield Button('Review Apply',id='handoff-apply-review')
                yield Button('Confirm selection',id='handoff-apply-confirm',variant='warning')
            with Horizontal():
                yield Button('Review previous selection',id='handoff-restore',disabled=True)
                yield Button('Confirm previous selection',id='handoff-restore-confirm',variant='warning')

    def on_mount(self):
        self.invalidate();self.ready=True

    def value(self,name):return self.query_one('#handoff-'+name,Input).value

    def inputs(self):return tuple(self.value(name) for name in ('source','renderer','geometry','destination'))

    def status(self,text):
        self.query_one('#handoff-status',Static).update('\n'.join(display(line) for line in text.splitlines()))

    def invalidate(self):
        self.plan=None;self.reviewed_inputs=None
        self.selection_expected=None;self.selection_record=None;self.restore_pending=False
        for name in ('handoff-confirm','handoff-apply-confirm','handoff-restore-confirm'):self.query_one('#'+name,Button).display=False
        self.query_one('#handoff-review',Static).update('')

    def on_input_changed(self,event):
        event.stop()
        if self.ready:
            had_review=self.plan is not None or self.selection_expected is not None;self.invalidate()
            if had_review:self.status('Review inputs changed. Review again before exporting.')

    def summary(self,record):
        return '\n'.join(display(line) for line in [
            'Saved scene: '+record['scene'],
            'Renderer: '+record['renderer']['path'],
            'Desktop geometry: '+record['geometry']+'; editor preview geometry: '+record['preview_geometry'],
            'Native snapshot files: '+str(len(record['native']))+'; selected asset references: '+str(len(record['assets'])),
            'Unbound stock lookups: '+(', '.join(record['unbound_stock_lookups']) or 'none explicitly listed; implicit resources remain unbound'),
            'Review ID: '+record['id'],*record['notes']])

    def on_button_pressed(self,event):
        event.stop();action=event.button.id
        if action=='handoff-back':self.action_cancel();return
        try:
            if action=='handoff-review-button':
                self.invalidate()
                plan=create_plan(self.root,Path(self.value('source')),self.value('renderer'),self.value('geometry'))
                destination=self.value('destination')
                self.query_one('#handoff-review',Static).update(self.summary(plan.metadata)+'\nNew directory: '+display(destination))
                self.plan=plan;self.reviewed_inputs=self.inputs()
                self.query_one('#handoff-confirm',Button).display=True
                self.status('Review above, then explicitly confirm a new private bundle. Nothing has been written.')
            elif action=='handoff-confirm':
                if self.plan is None or self.inputs()!=self.reviewed_inputs:raise ValueError('Inputs changed; review again.')
                target=stage_plan(self.plan,self.value('destination'))
                self.invalidate()
                self.result='Review-only bundle exported to '+str(target)+'. No scene selected or activated; source and draft unchanged.'
                self.status(self.result)
            elif action=='handoff-check':
                self.invalidate();record=check_bundle(self.root,Path(self.value('destination')))
                self.query_one('#handoff-review',Static).update(self.summary(record))
                self.result='Review-only bundle verified. No scene selected, setup or job changes.'
                self.status(self.result)
            elif action=='handoff-apply-review':
                self.invalidate()
                record=check_bundle(self.root,Path(self.value('destination')))
                expected=inspect_selection(self.root)
                self.selection_expected=expected;self.selection_record=record;self.reviewed_inputs=self.inputs()
                self.query_one('#handoff-review',Static).update(self.summary(record)+'\nDesktop execution uses the frozen revision as cwd and private .state/xplanet/desktop-tmp scratch; no renderer scratch is written into the revision.\nCurrent selection: '+expected.label+'\nConfirm changes ONLY the selected reference to an immutable copy of this saved scene. No renderer or service action. The running desktop remains unchanged; restart is separate.')
                self.query_one('#handoff-apply-confirm',Button).display=True
                self.status('Review saved bundle and current selection above. No files or selection changed by this review.')
            elif action=='handoff-apply-confirm':
                if self.selection_expected is None or self.inputs()!=self.reviewed_inputs:raise ValueError('Selection review changed; review Apply again.')
                if check_bundle(self.root,Path(self.value('destination')))!=self.selection_record:raise ValueError('Reviewed bundle changed; review Apply again.')
                receipt=apply_bundle(self.root,Path(self.value('destination')),self.selection_expected)
                self.selected(receipt,'Scene revision selected')
            elif action=='handoff-restore':
                self.invalidate()
                if self.receipt is None:raise ValueError('No completed selection change to restore in this dialog.')
                if inspect_selection(self.root)!=self.receipt.after:raise ValueError('Selection changed; previous-selection restore would overwrite a newer choice.')
                if self.receipt.before.revision:read_revision(self.root,self.receipt.before.revision)
                self.selection_expected=self.receipt.after;self.restore_pending=True
                self.query_one('#handoff-review',Static).update('Current selection: '+self.receipt.after.label+'\nRestore previous selection: '+self.receipt.before.label+'\nOnly the reference changes. Legacy files, producers and the running desktop remain untouched.')
                self.query_one('#handoff-restore-confirm',Button).display=True
                self.status('Confirm restoration explicitly; no change has occurred.')
            elif action=='handoff-restore-confirm':
                if not self.restore_pending or self.receipt is None:raise ValueError('Review previous selection again.')
                receipt=restore_selection(self.root,self.receipt)
                self.selected(receipt,'Previous selection restored');self.receipt=None
                self.query_one('#handoff-restore',Button).disabled=True
        except UncertainSelection as exc:
            self.invalidate();self.receipt=None;self.query_one('#handoff-restore',Button).disabled=True
            self.selection_label='uncertain'
            if self.on_selection:self.on_selection(self.selection_label)
            self.result='Selection outcome uncertain: '+str(exc)+' Inspect the selector before retrying; no automatic rollback or restart.'
            for note in getattr(exc,'__notes__',()):self.result+='\n'+note
            self.status(self.result)
        except (OSError,ValueError) as exc:
            self.invalidate()
            message='Handoff refused: '+str(exc)+'\nNo activation occurred.'
            for note in getattr(exc,'__notes__',()):message+='\n'+note
            self.result=message;self.status(message)

    def selected(self,receipt,message):
        self.invalidate();self.receipt=receipt;self.selection_label=receipt.after.label
        if self.on_selection:self.on_selection(self.selection_label)
        self.query_one('#handoff-restore',Button).disabled=receipt.before==receipt.after
        self.result=message+': '+receipt.after.label+'. No restart, renderer, provider or job action. Legacy and source files unchanged.'
        self.status(self.result)

    def action_cancel(self):self.dismiss((self.result,self.selection_label))

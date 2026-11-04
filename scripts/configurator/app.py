"""Textual presentation only; the model and preview/save I/O are independent."""
import asyncio
from datetime import datetime,timezone
import json
import re
import signal
import sys
from pathlib import Path
import subprocess

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, TextArea

from .model import PROJECTIONS, SAMPLE, View, ViewDocument, number, MONTHS, TARGETS, OBSERVERS, EAST_POSITIVE,MOON_PARENTS,SYSTEMS, NUMERIC_FIELDS
from .geography import COLORS
from .cloud_capture import describe_capture
from .observation_capture import PRODUCTS as OBS_PRODUCTS,describe as describe_observations,describe_metadata as describe_observation_metadata
from .library import save_named
from .history import DraftHistory
from .native_inspection import inspect_native,copy_unchanged
from .moon_scales_ui import MoonScalesScreen
from .native_patch import NativePatch
from .native_edit_ui import NativePatchPath,NativePatchScreen
from .handoff_ui import HandoffScreen
from .selection_info_ui import SelectedSceneScreen
from .resources import safe
from .library_ui import SceneLibrary
from .draft_session import DraftSession
from .recovery_ui import RecoveryScreen
from .comparison import plan as comparison_plan,reason as comparison_reason,render_set
from .comparison_ui import ComparisonReview
from .help_ui import StudioHelp
from .export_ui import RenderExport
from .render_export import export_snapshot
from .binary_diagnostics import cached as cached_binary_evidence,store as store_binary_evidence
from .workspace import Workspace, configuration_issues, open_view, save_view


STOCK_LIBRARY=Path(__file__).with_name('samples')/'scenes'


class ConfirmSave(ModalScreen[bool]):
    DEFAULT_CSS = '''
    ConfirmSave { align: center middle; }
    ConfirmSave > VerticalScroll { width: 70; height: auto; max-height: 90%;
        border: round $accent; padding: 1 2; background: $surface; }
    '''
    def __init__(self, destination, review=()):
        super().__init__()
        self.destination, self.review = destination, review

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static('Create matching named .conf/.def and associated assets at:' if Path(self.destination).suffix.lower()=='.conf' else 'Create legacy native xp.def/xp.conf directory at:',markup=False)
            yield Static(self.destination, markup=False)
            for line in self.review:
                yield Static(line, markup=False)
            yield Static('Desktop settings and schedules will not be changed.')
            with Horizontal():
                yield Button('Save new scene', id='confirm-save', variant='primary')
                yield Button('Back', id='back')

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == 'confirm-save')

    def key_escape(self):
        self.dismiss(False)


class ConfirmDiscard(ModalScreen[bool|str]):
    DEFAULT_CSS=ConfirmSave.DEFAULT_CSS.replace('ConfirmSave','ConfirmDiscard')
    BINDINGS=[('escape','keep','Keep editing')]
    def __init__(self,saved=False,recovery=False,modal=False):super().__init__();self.saved=saved;self.recovery=recovery;self.modal=modal
    def compose(self):
        with VerticalScroll():
            yield Static('Leave the scene editor?')
            yield Static('Source files and selected scene stay unchanged. Previously saved copies remain.' if self.saved else 'Only the current unsaved draft will be discarded. Source files and scene selection stay unchanged.')
            yield Static('Keep a private recovery draft, explicitly discard it, or continue editing. Ctrl-C exits using the last complete checkpoint; Ctrl-D/Ctrl-Q request exit.')
            if self.modal:yield Static('Open dialog fields are not included in scene recovery. Continue editing, or explicitly discard them on exit.')
            yield Button('Keep editing',id='keep-editing',variant='primary')
            yield Button('Keep recovery draft and exit',id='keep-draft',disabled=not self.recovery or self.modal)
            yield Button('Discard draft and exit',id='discard-draft')
    def on_mount(self):self.query_one('#keep-editing',Button).focus()
    def on_button_pressed(self,event):self.dismiss('keep' if event.button.id=='keep-draft' else event.button.id=='discard-draft')
    def action_keep(self):self.dismiss(False)


class OpenView(ModalScreen[str | None]):
    DEFAULT_CSS = ConfirmSave.DEFAULT_CSS.replace('ConfirmSave', 'OpenView')

    def __init__(self, initial, dirty=False,inspection=False):
        super().__init__()
        self.initial, self.dirty, self.inspection = initial, dirty,inspection

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static('Inspect native .conf/.def files without executing or changing them.' if self.inspection else 'Open a generated named .conf/.def file, or a legacy scene directory.')
            yield Static('Inspection leaves the current draft and source files unchanged.' if self.inspection else 'Opening replaces the draft scene and resets undo/redo history. Source files and the selected renderer stay unchanged.')
            if self.dirty and not self.inspection:
                yield Static('Replaced unsaved scene settings are discarded only if Open succeeds.')
            yield Input(self.initial, id='source-directory')
            with Horizontal():
                yield Button('Inspect source' if self.inspection else ('Open and replace draft' if self.dirty else 'Open view'), id='confirm-open', variant='primary')
                yield Button('Back', id='back-open')

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(self.query_one('#source-directory', Input).value
                     if event.button.id == 'confirm-open' else None)

    def key_escape(self):
        self.dismiss(None)


class NativeReviewScreen(ModalScreen[str | None]):
    DEFAULT_CSS=ConfirmSave.DEFAULT_CSS.replace('ConfirmSave','NativeReviewScreen')

    def __init__(self,review,destination):
        super().__init__();self.review,self.destination=review,destination

    def compose(self):
        with VerticalScroll():
            for section in self.review.sections():yield Static(section,markup=False)
            if self.review.recognized:
                yield Static('Optional: copy these exact snapshot bytes into a NEW private directory. Original filenames/version/assets are retained; no overwrite or Apply.')
                yield Input(self.destination,id='native-destination')
                yield Button('Copy original bytes',id='native-copy',variant='primary')
            yield Button('Back — leave source and draft unchanged',id='native-back')

    def on_button_pressed(self,event):
        self.dismiss(self.query_one('#native-destination',Input).value if event.button.id=='native-copy' and self.review.recognized else None)

    def key_escape(self):self.dismiss(None)


class ConfirmCapture(ModalScreen[bool]):
    DEFAULT_CSS=ConfirmSave.DEFAULT_CSS.replace('ConfirmSave','ConfirmCapture')

    def __init__(self,root,config,description='clouds'):
        super().__init__();self.root,self.config,self.description=root,config,description

    def compose(self):
        with VerticalScroll():
            yield Static('Read existing TotalMarker '+self.description+' and saved metadata from:',markup=False)
            yield Static(self.root+'\n'+self.config,markup=False)
            yield Static('No provider request, refresh, lock, recovery or source-file write. A verified frozen copy is retained for this draft.')
            with Horizontal():
                yield Button('Capture saved clouds' if self.description=='clouds' else 'Capture saved observations',id='confirm-capture',variant='primary')
                yield Button('Back',id='back-capture')

    def on_button_pressed(self,event):
        self.dismiss(event.button.id=='confirm-capture')

    def key_escape(self):
        self.dismiss(False)


def open_image(path):
    if Path('/usr/bin/open').is_file():
        subprocess.Popen(['/usr/bin/open', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ReportScreen(ModalScreen):
    BINDINGS = [Binding('escape', 'back', 'Back', show=False, priority=True)]
    DEFAULT_CSS = """
    ReportScreen { align: center middle; }
    ReportScreen > VerticalScroll { width: 90%; max-width: 100; height: 90%;
        border: round $accent; padding: 1 2; background: $surface; }
    ReportScreen Static { margin-bottom: 1; }
    """

    def __init__(self, title, sections, images=()):
        super().__init__()
        self.report_title, self.sections, self.images = title, sections, images

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(self.report_title, markup=False)
            for section in self.sections:
                yield Static(section, markup=False)
            for index, (label, snapshot) in enumerate(self.images):
                yield Static(f'{label}: {snapshot.view.summary()}\nRenderer: {snapshot.renderer}\nCompleted UTC: {snapshot.completed_utc}\n{snapshot.path}', markup=False)
                if snapshot.cloud_provenance:
                    yield Static(describe_capture(json.loads(snapshot.cloud_provenance)),markup=False)
                if snapshot.observation_provenance:
                    yield Static('Active frozen observations in this preview: '+', '.join(snapshot.view.uses_observations())+'\n'+describe_observation_metadata(json.loads(snapshot.observation_provenance)),markup=False)
                yield Button('Open ' + label, id=f'report-image-{index}', disabled=not Path('/usr/bin/open').is_file())
            yield Button('Back', id='close-report')

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == 'close-report':
            self.dismiss()
        elif event.button.id.startswith('report-image-'):
            open_image(self.images[int(event.button.id.rsplit('-', 1)[1])][1].path)

    def action_back(self):
        self.dismiss()


class ConfiguratorApp(App):
    TITLE = 'Xplanet · Scene studio'
    BINDINGS = [Binding('f1','help','Help',priority=True),
                Binding('escape', 'request_exit', 'Cancel'),
                Binding('ctrl+z', 'undo', 'Undo', show=False, priority=True),
                Binding('ctrl+y', 'redo', 'Redo', show=False, priority=True),
                Binding('ctrl+q', 'request_exit', 'Cancel', show=False, priority=True),
                Binding('ctrl+c', 'interrupt', 'Cancel', show=False, priority=True),
                Binding('ctrl+d', 'request_exit', 'Cancel', show=False, priority=True)]
    CSS = '''
    Screen { background: $background; }
    #content { padding: 1 2; }
    Label { margin-top: 1; }
    Input, Select { max-width: 90; }
    Horizontal { height: auto; margin-top: 1; }
    Button { margin-right: 1; }
    .control { height: auto; }
    .geo-editor { height: 7; max-width: 90; }
    #status { padding: 1; border: round $accent; margin-top: 1; }
    '''

    def __init__(self, root: Path, renderer: str, workspace=None, *, document=None,recovery=True):
        super().__init__()
        self.root, self.renderer = root, renderer
        self.workspace = workspace or Workspace()
        if self.workspace.capabilities is None:self.workspace.capabilities=cached_binary_evidence(root)
        self.preview_job = None
        self.saved = None
        self.selection_label = None
        self.controls_ready = False
        self.leaving = False
        self.exit_prompting=False
        self.cancelling_operation=False
        self.termination_signal=None
        self.recovery_origin=None
        self.recovery_notice=''
        self.signal_handlers={}
        self.recovery=DraftSession(root,self.recovery_snapshot,self.recovery_status) if recovery else None
        self.history = None
        self.document = document or ViewDocument(View(), renderer, SAMPLE.read_bytes())
        self.capture_id=self.document.view.capture_id
        self.observations_id=self.document.view.observations_id
        self.moon_scales=self.document.view.moon_scales
        self.workspace.reset_captures(self.document.capture,self.document.observations)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id='content'):
            yield Static(self.source_description(), id='view-source', markup=False)
            yield Button('Help (F1)',id='help')
            with Horizontal():
                yield Button('Open saved view…', id='load')
                yield Button('Scene library…',id='library')
                yield Button('Stock scenes…',id='stock')
                yield Button('Configuration health', id='health')
            with Horizontal():
                yield Button('Inspect native files…',id='inspect-native')
                yield Button('Edit native values…',id='edit-native')
                yield Button('Handoff review…',id='handoff')
                yield Button('Selected scene…',id='selected-scene')
            yield Static('', id='dirty-state', markup=False)
            with Horizontal():
                yield Button('Undo', id='undo', disabled=True)
                yield Button('Redo', id='redo', disabled=True)
                yield Button('Review changes', id='review')
                yield Button('Recovery drafts…',id='recovery',disabled=self.recovery is None)
            yield Static('Recovery: local private checkpoints; native files are never autosaved.' if self.recovery else 'Recovery disabled for this isolated session.',id='recovery-state',markup=False)
            yield Static('', id='scene-summary', markup=False)
            yield Static('', id='health-summary', markup=False)
            yield Static('Edit, preview, then save or cancel. Saving does not apply desktop settings.')
            yield Label('Xplanet executable (absolute path)')
            yield Input(self.renderer, id='renderer')
            with Vertical(id='control-target',classes='control'):
                yield Label('Start with a target — sections remain freely revisitable')
                yield Select([(target.title(),target) for target in TARGETS],value=self.document.view.target,allow_blank=False,id='target')
            yield Static('',id='target-context',markup=False)
            with Vertical(id='control-composition',classes='control'):
                yield Label('Planetary appearance: target or bundled companion system')
                yield Select([('Target appearance (existing behavior)','target'),('System textures (same camera)','system')],value=self.document.view.composition,allow_blank=False,id='composition')
            with Vertical(id='control-satellite-scale',classes='control'):
                yield Label('Moon visual enlargement: 1–10× (1 = engine natural size; no hiding)')
                yield Input(number(self.document.view.satellite_scale),id='satellite-scale')
            with Vertical(id='control-moon-scales',classes='control'):
                yield Button('Individual moon scales…',id='moon-scales')
            yield Static('',id='system-context',markup=False)
            with Vertical(id='control-orbit-paths',classes='control'):
                yield Label('Illustrative moon orbital guides (system space views only)')
                yield Select([('Off','off'),('One nominal orbit, fixed 5° sampling','on')],value=self.document.view.orbit_paths,allow_blank=False,id='orbit-paths')
            with Vertical(id='control-orbit-color',classes='control'):
                yield Label('Orbital guide color')
                yield Select([(color.title(),color) for color in COLORS],value=self.document.view.orbit_color,allow_blank=False,id='orbit-color')
            with Vertical(id='control-orbit-width',classes='control'):
                yield Label('Orbital guide line width: 1–3 whole pixels')
                yield Input(number(self.document.view.orbit_width),id='orbit-width')
            yield Static('',id='orbit-context',markup=False)
            with Vertical(id='control-projection', classes='control'):
                yield Label('Scene mode: projected map or space view')
                yield Select([('Space (no projection)' if p == 'space' else p.title() + ' map', p) for p in PROJECTIONS], value=self.document.view.projection,
                             allow_blank=False, id='projection')
            with Vertical(id='control-observer', classes='control'):
                yield Label('Observer (space views only)')
                labels={'geographic':'Geographic latitude/longitude','opposite_sun':'Opposite the Sun — night side','sun':'From the Sun — day side'}
                yield Select([(labels.get(origin,'From '+origin.title()),origin) for origin in OBSERVERS],
                             value=self.document.view.observer, allow_blank=False, id='observer')
            yield Static('', id='camera-context', markup=False)
            with Vertical(id='control-latitude', classes='control'):
                yield Label('Latitude (−90 to 90 degrees)')
                yield Input(number(self.document.view.latitude), id='latitude')
            with Vertical(id='control-longitude-mode', classes='control'):
                yield Label('Longitude strategy')
                yield Select([('Fixed longitude','longitude'),('Local solar hour','solar')],value=self.document.view.longitude_mode,allow_blank=False,id='longitude-mode')
            with Vertical(id='control-solar-hour', classes='control'):
                yield Label('Local solar hour: 0 midnight, 12 noon (not a timezone)')
                yield Input(number(self.document.view.solar_hour),id='solar-hour')
            with Vertical(id='control-distance', classes='control'):
                yield Label('Geographic observer distance: 1.01–1000000 body radii from center')
                yield Input(number(self.document.view.distance),id='distance')
            with Vertical(id='control-north', classes='control'):
                yield Label('Space orientation')
                yield Select([(x.title()+' north',x) for x in ('body','galactic','orbit')],value=self.document.view.north,allow_blank=False,id='north')
            with Vertical(id='control-rotation', classes='control'):
                yield Label('Counterclockwise rotation: −180 to 180 degrees')
                yield Input(number(self.document.view.rotation),id='rotation')
            with Vertical(id='control-camera-mode',classes='control'):
                yield Label('Moon observer: centre or orbital camera (fixed UTC only)')
                yield Select([('Body centre','centre'),('Lunar orbital camera','lunar_orbit')],value=self.document.view.camera_mode,allow_blank=False,id='camera-mode')
            with Vertical(id='control-orbit-latitude',classes='control'):
                yield Label('Lunar observer latitude: -90 to 90 degrees')
                yield Input(number(self.document.view.orbit_latitude),id='orbit-latitude')
            with Vertical(id='control-orbit-longitude',classes='control'):
                yield Label('Lunar observer longitude: east-positive, -180 to 180 degrees')
                yield Input(number(self.document.view.orbit_longitude),id='orbit-longitude')
            with Vertical(id='control-orbit-range',classes='control'):
                yield Label('Lunar range: 1.1–100 radii from centre (not altitude)')
                yield Input(number(self.document.view.orbit_range),id='orbit-range')
            with Vertical(id='control-frame-x',classes='control'):
                yield Label('Frame centre X: 0–100% from left')
                yield Input(number(self.document.view.frame_x),id='frame-x')
            with Vertical(id='control-frame-y',classes='control'):
                yield Label('Frame centre Y: 0–100% from top')
                yield Input(number(self.document.view.frame_y),id='frame-y')
            with Vertical(id='control-longitude', classes='control'):
                yield Label('Longitude (−180 to 180 degrees)')
                yield Input(number(self.document.view.longitude), id='longitude')
            with Vertical(id='control-framing', classes='control'):
                yield Label('Space framing')
                yield Select([('Target radius (% of image height)', 'radius'), ('Field of view (degrees)', 'fov')],
                             value=self.document.view.framing, allow_blank=False, id='framing')
            with Vertical(id='control-radius', classes='control'):
                yield Label('Target radius: 0.1–100 % of image height')
                yield Input(number(self.document.view.radius), id='radius')
            with Vertical(id='control-fov', classes='control'):
                yield Label('Field of view: 0.1–179 degrees')
                yield Input(number(self.document.view.fov), id='fov')
            yield Static('', id='framing-context', markup=False)
            with Vertical(id='control-time-mode', classes='control'):
                yield Label('Scene time — separate from labels and data freshness')
                yield Select([('Now (renderer clock for each preview)', 'now'), ('Fixed UTC instant', 'fixed')],
                             value=self.document.view.time_mode, allow_blank=False, id='time-mode')
            with Vertical(id='control-utc', classes='control'):
                yield Label('Fixed UTC: YYYY-MM-DDTHH:MM:SSZ (1800–2200; Pluto/Charon geometry before 2100)')
                yield Input(self.document.view.utc, id='utc')
            yield Static('', id='time-context', markup=False)
            with Vertical(id='control-planet-shade',classes='control'):
                yield Label('Planetary shadow brightness: 0–100 whole percent (no night texture)')
                yield Input(number(self.document.view.planet_shade),id='planet-shade')
            yield Label('Earth appearance',id='earth-appearance-heading')
            with Vertical(id='control-map-family', classes='control'):
                yield Label('Day map: stock or bundled 2004 seasonal composite')
                yield Select([('Stock renderer Earth', 'stock'), ('Monthly Earth', 'world'),
                              ('Monthly Earth + topography', 'world.topo'),
                              ('Monthly Earth + topography/bathymetry', 'world.topo.bathy')],
                             value=self.document.view.map_family, allow_blank=False, id='map-family')
            with Vertical(id='control-month', classes='control'):
                yield Label('Imagery month (independent of scene UTC)')
                yield Select([(month, month) for month in MONTHS], value=self.document.view.month,
                             allow_blank=False, id='month')
            with Vertical(id='control-night', classes='control'):
                yield Label('Night texture (not a brightness slider)')
                yield Select([('Stock renderer night imagery', 'stock'), ('Bundled Earthlights 2002', 'lights2002')],
                             value=self.document.view.night, allow_blank=False, id='night')
            with Vertical(id='control-twilight', classes='control'):
                yield Label('Day/night twilight blend: 0–90 whole degrees')
                yield Input(number(self.document.view.twilight), id='twilight')
            with Vertical(id='control-grid', classes='control'):
                yield Label('Geographic grid: major lines / 1-degree dots')
                yield Select([('Off', 'off'), ('30-degree majors', '30'), ('15-degree majors', '15'),
                              ('10-degree majors', '10')], value=self.document.view.grid, allow_blank=False, id='grid')
            with Vertical(id='control-label', classes='control'):
                yield Label('Scene label (renderer font support required)')
                yield Select([('Off', 'off'), ('UTC scene information', 'utc')],
                             value=self.document.view.label, allow_blank=False, id='label')
            yield Static('', id='appearance-context', markup=False)
            yield Label('Local bundled Earth layers',id='earth-layer-heading')
            with Vertical(id='control-relief',classes='control'):
                yield Label('Relief shading (large bundled height map)')
                yield Select([('Off','off'),('Bundled GEBCO relief','gebco')],value=self.document.view.relief,allow_blank=False,id='relief')
            with Vertical(id='control-relief-scale',classes='control'):
                yield Label('Relief exaggeration: 0.1–5 (studio range; shading only)')
                yield Input(number(self.document.view.relief_scale),id='relief-scale')
            with Vertical(id='control-relief-shadow',classes='control'):
                yield Label('Relief shadows')
                yield Select([('Use night imagery','night'),('Shade the day map','shade')],value=self.document.view.relief_shadow,allow_blank=False,id='relief-shadow')
            with Vertical(id='control-relief-shade',classes='control'):
                yield Label('Relief shadow brightness: 0–100 whole percent')
                yield Input(number(self.document.view.relief_shade),id='relief-shade')
            with Vertical(id='control-specular',classes='control'):
                yield Label('Ocean specular reflection (large bundled mask)')
                yield Select([('Off','off'),('Bundled reflectance mask','bundled')],value=self.document.view.specular,allow_blank=False,id='specular')
            with Vertical(id='control-clouds',classes='control'):
                yield Label('Cloud display (static imagery, not a refresh)')
                yield Select([('Off','off'),('Bundled 26 Aug 2011 snapshot (2048)','snapshot2011'),('Frozen TotalMarker capture — Now only','captured')],value=self.document.view.clouds,allow_blank=False,id='clouds')
            for product in OBS_PRODUCTS:
                with Vertical(id='control-'+product+'-layer',classes='control'):
                    yield Label({'quake':'Earthquakes','volcano':'Volcanoes','storm':'Storm markers and tracks'}[product]+' — frozen existing output, Earth Now only')
                    yield Select([('Off — retain capture','off'),('Use frozen capture','captured')],value=getattr(self.document.view,product+'_layer'),allow_blank=False,id=product+'-layer')
            yield Static('',id='observations-summary',markup=False)
            with Vertical(id='capture-source',classes='control'):
                yield Label('Explicit capture source (not stored in the scene)')
                yield Input(str(self.root),id='capture-root')
                yield Input('config/totalmarker.toml',id='capture-config')
                yield Button('Capture existing clouds…',id='capture-cloud')
                yield Button('Capture selected observations…',id='capture-observations')
            yield Static('',id='capture-summary',markup=False)
            with Vertical(id='control-cloud-gamma',classes='control'):
                yield Label('Cloud gamma: 0.1–5 (studio range)')
                yield Input(number(self.document.view.cloud_gamma),id='cloud-gamma')
            with Vertical(id='control-cloud-threshold',classes='control'):
                yield Label('Cloud threshold: 0–255 whole brightness level')
                yield Input(number(self.document.view.cloud_threshold),id='cloud-threshold')
            yield Static('Bundled choices display existing files. Only explicit cloud Capture reads a saved TotalMarker product; no provider refresh or schedule is changed.',id='earth-layer-context')
            yield Label('Earth surface annotations',id='geography-heading')
            with Vertical(id='control-places', classes='control'):
                yield Label('Places and labels')
                yield Select([('Off — retain list', 'off'), ('On', 'on')],value=self.document.view.places,allow_blank=False,id='places')
            with Vertical(id='control-places-text', classes='control'):
                yield Label('One per line: latitude longitude "Label" (max 32; no extra options)')
                yield TextArea(self.document.view.places_text,id='places-text',classes='geo-editor',show_line_numbers=True,
                               placeholder='51.5 -0.1 "London"')
            with Vertical(id='control-place-color', classes='control'):
                yield Label('Place color')
                yield Select([(c.title(),c) for c in COLORS],value=self.document.view.place_color,allow_blank=False,id='place-color')
            with Vertical(id='control-place-size', classes='control'):
                yield Label('Place label font size: 10–24 whole pixels (renderer font support required)')
                yield Input(number(self.document.view.place_size),id='place-size')
            with Vertical(id='control-routes', classes='control'):
                yield Label('Static great-circle route arcs')
                yield Select([('Off — retain list', 'off'), ('On', 'on')],value=self.document.view.routes,allow_blank=False,id='routes')
            with Vertical(id='control-routes-text', classes='control'):
                yield Label('One per line: latitude1 longitude1 latitude2 longitude2 (max 32)')
                yield TextArea(self.document.view.routes_text,id='routes-text',classes='geo-editor',show_line_numbers=True,
                               placeholder='51.5 -0.1 40.7 -74')
            with Vertical(id='control-route-color', classes='control'):
                yield Label('Route color')
                yield Select([(c.title(),c) for c in COLORS],value=self.document.view.route_color,allow_blank=False,id='route-color')
            with Vertical(id='control-route-width', classes='control'):
                yield Label('Route thickness: 1–5 whole pixels')
                yield Input(number(self.document.view.route_width),id='route-width')
            yield Static('Surface degrees only; static annotations, not provider data, pixel/sky coordinates, travel trajectories or eclipse predictions.')
            yield Static('Finite previews only; no provider requests or desktop changes.')
            with Vertical(id='control-geometry',classes='control'):
                yield Label('Preview WIDTHxHEIGHT — 1920x1080 default; up to 16,777,216 pixels, independent of texture aspect')
                yield Input(self.document.view.geometry,id='geometry')
            with Horizontal():
                yield Button('Preview', id='preview', variant='primary')
                yield Button('Diagnose resources',id='resources')
                yield Button('Open latest', id='open-image', disabled=True)
                yield Button('Compare…', id='compare', disabled=True)
            with Horizontal():
                yield Button('Framing sheet…',id='framing-sheet')
                yield Button('Open framing sheet',id='open-sheet',disabled=True)
            with Horizontal():
                yield Button('Export latest…',id='export-image',disabled=True)
                yield Button('Export framing sheet…',id='export-sheet',disabled=True)
            yield Static('',id='comparison-context',markup=False)
            yield Button('Cancel preview', id='cancel-preview')
            yield Static('', id='preview-state', markup=False)
            yield Label('Save as a NEW scene-name.conf pair; directory paths retain legacy saves')
            yield Input(self.copy_destination(), id='destination')
            with Horizontal():
                yield Button('Save & close…', id='save')
                yield Button('Save & continue…',id='save-continue')
                yield Button('Cancel', id='cancel')
            yield Static(self.open_message(), id='status', markup=False)
        yield Footer()

    def source_description(self):
        if self.recovery_origin is not None:return 'Recovered draft snapshot; source hint only, not reread: '+safe(self.recovery_origin)
        return (f'Opened snapshot: {self.document.source}' if self.document.source else
                'Shipped Earth sample · selectable bundled textures · no live overlays')

    def copy_destination(self):
        source=self.document.source
        if source is None and self.recovery_origin:source=Path(self.recovery_origin)
        name=(source.stem if self.document.named_source else source.name) if source else 'earth-view'
        name=re.sub('[^A-Za-z0-9_-]+','-',name).strip('-')[:40] or 'scene'
        if source:name+='-copy'
        return str(self.root/'config'/'scenes'/(name+'.conf'))

    def open_message(self):
        if self.document.source:
            return ('Saved scene loaded as a snapshot. The local renderer selection was retained; '
                    'the executable named in a file is never adopted automatically.')
        return 'Ready. No personal configuration was read.'

    def load(self, source):
        if source is None:
            self.status('Open cancelled. Draft and source files are unchanged.')
            return
        try:
            document = open_view(source)
        except (ValueError, OSError) as exc:
            self.status(f'Cannot open view: {exc}')
            return
        if self.recovery:self.recovery.boundary()
        self.recovery_origin=None
        self.workspace.reset_captures(document.capture,document.observations)
        self.document = document
        values = {field: number(value) if field in NUMERIC_FIELDS else value
                  for field, value in vars(document.view).items()}
        values['renderer'] = self.query_one('#renderer', Input).value
        self.restore_fields(values)
        self.history.reset(self.raw_fields())
        self.update_controls()
        self.query_one('#destination', Input).value = self.copy_destination()
        self.query_one('#view-source', Static).update(self.source_description())
        self.update_preview_state()
        self.status(self.open_message())

    def on_mount(self):
        self.history = DraftHistory(self.raw_fields())
        self.controls_ready = True
        self.update_controls()
        if self.recovery:
            try:
                rows=self.recovery.store.entries()
                if rows:self.recovery_status(f'{len(rows)} recovery sessions available; choose Recovery drafts to inspect. Nothing restored automatically.')
            except (OSError,ValueError) as exc:self.recovery_status('Recovery inspection unavailable: '+str(exc))
        if not self.is_headless:
            loop=asyncio.get_running_loop()
            for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
                self.signal_handlers[sig]=signal.getsignal(sig)
                loop.add_signal_handler(sig,self.external_termination,sig)
            self.set_interval(1,self.check_terminal)

    async def on_unmount(self):
        if self.recovery:await self.recovery.stop();self.recovery.close()
        loop=asyncio.get_running_loop()
        for sig,previous in self.signal_handlers.items():
            loop.remove_signal_handler(sig);signal.signal(sig,previous)
        self.signal_handlers={}

    def check_terminal(self):
        try:connected=sys.stdin.isatty() and sys.stdout.isatty()
        except (OSError,ValueError):connected=False
        if not connected:self.external_termination(signal.SIGHUP)

    def external_termination(self,sig):
        self.termination_signal=sig
        self.run_worker(self.action_force_cancel())

    def recovery_status(self,message):
        self.recovery_notice=message
        if self.is_mounted:self.query_one('#recovery-state',Static).update(safe(message))

    def recovery_snapshot(self):
        if self.history is None:return None
        self.history.record(self.raw_fields())
        if not self.history.dirty and self.recovery.session is None:return None
        return (self.raw_fields(),self.history.baseline,self.document.config,self.workspace,self.document.source or self.recovery_origin or '')

    def restore_recovery(self,recovered):
        if recovered is None:return
        use_recorded=False
        if isinstance(recovered,tuple):recovered,use_recorded=recovered
        try:
            if self.recovery:self.recovery.boundary()
            from .workspace import CAPTURE_BUDGET
            if sum(len(item.image) for item in recovered.clouds)+sum(item.byte_size for item in recovered.observations)>CAPTURE_BUDGET:raise ValueError('Recovered captures exceed the session budget.')
            self.workspace.reset_captures()
            for item in recovered.clouds:self.workspace.register_capture(item)
            for item in recovered.observations:self.workspace.register_observations(item)
            baseline=dict(recovered.record['baseline']);current=dict(recovered.record['current'])
            if not use_recorded:baseline['renderer']=current['renderer']=self.query_one('#renderer',Input).value
            self.document=ViewDocument(View.from_fields({key:value for key,value in baseline.items() if key!='renderer'}),'',recovered.config)
            self.restore_fields(current);self.history=DraftHistory(baseline);self.history.record(current)
            self.recovery_origin=recovered.record['source'];self.query_one('#view-source',Static).update(self.source_description())
            self.query_one('#destination',Input).value=self.copy_destination();self.update_controls();self.update_preview_state()
            self.status(('Previous complete checkpoint recovered. ' if recovered.fallback else 'Checkpoint recovered. ')+'Recovery copied into the editor; invalid inputs and inactive choices retained. Local executable retained by default; recorded text is opt-in and Preview stays explicit. No source reread, native save, selection, provider or desktop operation.')
            if self.recovery:self.recovery.changed()
        except (OSError,ValueError) as exc:self.status('Recovery could not be restored: '+str(exc)+'. Original recovery material retained.')

    def on_select_changed(self, event: Select.Changed):
        if self.controls_ready and event.select.id in ('camera-mode', 'orbit-paths', 'orbit-color', 'composition', 'target', 'projection', 'observer', 'framing', 'longitude-mode', 'north', 'time-mode', 'map-family', 'month', 'night', 'grid', 'label', 'places', 'routes', 'place-color', 'route-color', 'relief', 'relief-shadow', 'specular', 'clouds', 'quake-layer', 'volcano-layer', 'storm-layer'):
            self.capture_edit()

    def on_input_changed(self, event: Input.Changed):
        if self.controls_ready and event.input.id in ('orbit-latitude','orbit-longitude','orbit-range','frame-x','frame-y','geometry', 'latitude', 'longitude', 'solar-hour', 'distance', 'rotation', 'radius', 'fov', 'utc', 'twilight', 'place-size', 'route-width', 'relief-scale', 'relief-shade', 'cloud-gamma', 'cloud-threshold', 'planet-shade', 'satellite-scale', 'orbit-width', 'renderer'):
            self.capture_edit(event.input.id)

    def on_text_area_changed(self,event:TextArea.Changed):
        if self.controls_ready:
            self.capture_edit(event.text_area.id)

    def on_descendant_blur(self, event):
        if self.history is not None:
            self.history.break_group()

    def raw_fields(self):
        fields = {field.replace('-', '_'): self.query_one('#' + field, Input).value
                  for field in ('orbit-latitude','orbit-longitude','orbit-range','frame-x','frame-y','geometry', 'latitude', 'longitude', 'solar-hour', 'distance', 'rotation', 'radius', 'fov', 'utc', 'twilight', 'place-size', 'route-width', 'relief-scale', 'relief-shade', 'cloud-gamma', 'cloud-threshold', 'planet-shade', 'satellite-scale', 'orbit-width')}
        fields.update({field.replace('-', '_'): str(self.query_one('#' + field, Select).value)
                       for field in ('camera-mode', 'orbit-paths', 'orbit-color', 'composition', 'target', 'projection', 'observer', 'framing', 'longitude-mode', 'north', 'time-mode', 'map-family', 'month', 'night', 'grid', 'label', 'places', 'routes', 'place-color', 'route-color', 'relief', 'relief-shadow', 'specular', 'clouds', 'quake-layer', 'volcano-layer', 'storm-layer')})
        fields.update({field.replace('-', '_'):self.query_one('#'+field,TextArea).text for field in ('places-text','routes-text')})
        fields['capture_id']=self.capture_id
        fields['observations_id']=self.observations_id
        fields['moon_scales']=self.moon_scales
        fields['renderer'] = self.query_one('#renderer', Input).value
        return fields

    def draft(self):
        return View.from_fields({key: value for key, value in self.raw_fields().items() if key != 'renderer'})

    def capture_edit(self, group=None):
        self.history.record(self.raw_fields(), group)
        self.update_controls()
        if self.recovery:self.recovery.changed()

    def restore_fields(self, values):
        for field, value in values.items():
            if field in ('capture_id','observations_id','moon_scales'):
                setattr(self,field,value)
                continue
            widget = self.query_one('#' + field.replace('_', '-'))
            with widget.prevent(Input.Changed, Select.Changed, TextArea.Changed):
                if isinstance(widget,TextArea):widget.load_text(value)
                else:widget.value = value

    def action_undo(self):
        if self.history is not None and not isinstance(self.screen, ModalScreen):
            self.history.record(self.raw_fields())
            self.restore_fields(self.history.undo())
            self.update_controls()
            if self.recovery:self.recovery.changed()

    def action_redo(self):
        if self.history is not None and not isinstance(self.screen, ModalScreen):
            self.history.record(self.raw_fields())
            self.restore_fields(self.history.redo())
            self.update_controls()
            if self.recovery:self.recovery.changed()

    def change_review(self):
        self.history.record(self.raw_fields())
        active = self.draft().active_fields() | {'renderer'}
        lines = ['Baseline snapshot: ' + (str(self.document.source) if self.document.source else 'shipped sample'),
                 'Executable changes are relative to the local selection when this scene was opened; saved executables are never adopted.']
        for field, before, after in self.history.changes():
            role = 'local executable selection' if field == 'renderer' else ('active' if field in active else 'retained / currently inactive')
            lines.append(f'{field.replace("_", " ").title()} ({role}): {before!r} → {after!r}')
        if not self.history.dirty:
            lines.append('No unsaved scene changes. A new copy can still be saved.')
        if self.observations_id:
            lines.append('Save includes frozen observation markers/arcs and referenced PNG icons (embedded image metadata unchanged), plus bounded provenance; review before sharing.')
        if self.capture_id:
            lines.append('Save includes the frozen cloud JPEG (embedded image metadata unchanged) and minimal provenance; no source configuration, credentials or source paths are included.')
        lines.append('Only proposed native files are saved. This is not Apply; source files and desktop settings stay unchanged.')
        return lines

    def current_issues(self):
        view=self.draft()
        return configuration_issues(view,self.query_one('#renderer',Input).value,self.document.config,self.workspace.capture_for(view),self.workspace.observations_for(view),self.workspace.capabilities)

    def update_controls(self):
        view = self.draft()
        why=comparison_reason(view)
        self.query_one('#framing-sheet',Button).disabled=bool(why) or self.workspace.busy
        self.query_one('#comparison-context',Static).update(why or 'Three static 1920×1080 framing snapshots at one reviewed epoch; contact sheet opens explicitly.')
        self.query_one('#framing-sheet',Button).tooltip=why or 'Three framing values, one reviewed epoch, temporary local contact sheet.'
        sheet=self.workspace.comparison_latest
        self.query_one('#open-sheet',Button).disabled=sheet is None
        self.query_one('#open-sheet',Button).label='Open framing sheet' if sheet is None or sheet.matches(view,self.query_one('#renderer',Input).value) else 'Open prior framing sheet'
        issues = self.current_issues()
        invalid = {issue.field for issue in issues if issue.severity == 'blocking'}
        active = view.active_fields()
        for field, widget_type in [('camera-mode',Select),('orbit-latitude',Input),('orbit-longitude',Input),('orbit-range',Input),('frame-x',Input),('frame-y',Input),('geometry',Input),('moon-scales',Button),('orbit-paths',Select),('orbit-color',Select),('orbit-width',Input),('composition',Select),('satellite-scale',Input),('target',Select),('projection', Select), ('observer', Select), ('framing', Select),
                                   ('longitude-mode',Select),('north',Select),('solar-hour',Input),('distance',Input),('rotation',Input),
                                   ('time-mode', Select), ('latitude', Input), ('longitude', Input),
                                   ('radius', Input), ('fov', Input), ('utc', Input), ('map-family', Select),
                                   ('month', Select), ('night', Select), ('twilight', Input), ('grid', Select), ('label', Select), ('places',Select), ('routes',Select),
                                   ('places-text',TextArea),('routes-text',TextArea),('place-color',Select),('place-size',Input),
                                   ('route-color',Select),('route-width',Input),('relief',Select),('relief-scale',Input),
                                   ('relief-shadow',Select),('relief-shade',Input),('specular',Select),('clouds',Select),
                                   ('cloud-gamma',Input),('cloud-threshold',Input),('planet-shade',Input),
                                   *((product+'-layer',Select) for product in OBS_PRODUCTS)]:
            key = field.replace('-', '_')
            visible = key in active or key in invalid
            self.query_one('#control-' + field).display = visible
            self.query_one('#' + field, widget_type).disabled = not visible
        self.query_one('#system-context',Static).update(('System mode uses bundled companions: '+', '.join(SYSTEMS[view.target])+'. Frame manually; per-body hiding is unavailable.' if view.uses_system() else 'System choices are retained but inactive for this target/map mode.' if view.composition=='system' else 'System appearance is available in space mode for Mars, Jupiter, Saturn, Uranus and Pluto. It does not isolate visible bodies.'))
        self.query_one('#orbit-context',Static).update('Approximate local orbit guides, parent held at scene epoch. Not spacecraft trails or event predictions; fixed-date sample coverage is checked by health.' if view.uses_orbits() else 'Orbital choices are retained; paths are currently off or inactive.')
        self.query_one('#orbit-context').display=view.uses_system()
        earth=view.target=='earth'
        self.query_one('#target-context',Static).update('Earth appearance and surface annotations are available below.' if earth else 'Bundled '+view.target.title()+' texture.'+(' Moon of '+MOON_PARENTS[view.target].title()+'.' if view.target in MOON_PARENTS else '')+' Earth choices are retained and inactive. Built-in approximate geometry; no external ephemeris or trajectory support is implied.')
        for widget in ('earth-appearance-heading','earth-layer-heading','earth-layer-context','geography-heading','appearance-context'):
            self.query_one('#'+widget).display=earth
        self.query_one('#camera-context', Static).update(
            ('Lunar orbital camera uses a generated one-row fixed-time origin; no terrain or event reconstruction.' if view.uses_lunar_camera() else 'Space: body origins use body centres; target-geographic choices are retained.' if view.projection == 'space'
             else 'Maps use geographic coordinates. Space observer/framing controls are hidden and retained.')+
            (' Lunar observer longitude is east-positive, west-negative.' if view.uses_lunar_camera() else ' Longitude is east-positive, west-negative.' if view.target in EAST_POSITIVE else ' Longitude is west-positive, east-negative in Xplanet for this body.'))
        self.query_one('#framing-context', Static).update('Only one framing strategy is active; inactive values are retained.')
        self.query_one('#framing-context').display = view.projection == 'space'
        self.query_one('#time-context', Static).update(
            'Fixed UTC changes geometry, not imagery dates or observation freshness.' if view.time_mode == 'fixed'
            else 'Now is captured for each preview. The hidden fixed UTC value is retained.')
        model_blocked = any(issue.severity == 'blocking' for issue in view.issues())
        summary = 'Draft has invalid values; Configuration health explains each blocking field.' if model_blocked else view.summary()
        self.query_one('#scene-summary', Static).update(summary + '\nAssets: ' + view.appearance_summary() + '; no live overlays.')
        self.query_one('#appearance-context', Static).update(
            'Seasonal imagery is selected independently of scene time. Twilight blends the day/night boundary; '
            'shade=30 remains only an engine fallback if a night texture cannot be found. Bundled assets use this checkout.')
        counts = {level: sum(issue.severity == level for issue in issues) for level in ('blocking', 'warning', 'info')}
        self.query_one('#health-summary', Static).update(
            f'Configuration health: {counts["blocking"]} blocking, {counts["warning"]} warnings, {counts["info"]} information. '
            'Hidden invalid fields are exposed for correction.')
        if self.history is not None:
            count = len(self.history.changes())
            self.query_one('#dirty-state', Static).update(
                f'Unsaved scene changes: {count} field(s).' if count else 'No unsaved scene changes.')
            self.query_one('#undo', Button).disabled = not self.history.can_undo
            self.query_one('#redo', Button).disabled = not self.history.can_redo
        self.query_one('#capture-source').display=bool(view.uses_capture() or view.uses_observations())
        self.query_one('#capture-cloud').display=view.uses_capture()
        self.query_one('#capture-observations').display=bool(view.uses_observations())
        frozen=self.workspace.observations_for(view)
        text=describe_observations(frozen) if frozen else 'No frozen observations retained. Capture reads existing verified products; no refresh is run.'
        if not view.uses_observations():text+='\nObservations inactive for this scene; selections and captured bytes are retained.'
        self.query_one('#observations-summary',Static).update(text)
        self.query_one('#observations-summary').display=earth and (bool(view.observations_id) or any(getattr(view,p+'_layer')=='captured' for p in OBS_PRODUCTS))
        captured=self.workspace.capture_for(view)
        text=describe_capture(captured.metadata) if captured else 'No frozen capture retained. Capture is explicit and Now-only; the bundled 2011 image is a separate static choice.'
        if view.clouds=='captured' and not view.uses_capture():text+='\nInactive outside Earth Now scenes; no captured current data or update labels are rendered.'
        self.query_one('#capture-summary',Static).update(text)
        self.query_one('#capture-summary').display=earth and (bool(view.capture_id) or view.clouds=='captured')
        self.update_preview_state()

    def update_preview_state(self):
        latest = self.workspace.latest
        if latest:
            matches = latest.matches(self.draft(), self.query_one('#renderer', Input).value, self.document.config)
            state = 'active settings match' if matches else 'STALE for this draft — prior successful output retained'
            text = f'Latest successful preview: {latest.completed_utc}; {state}. Now images are snapshots, not live data.'
        else:
            text = 'No successful preview in this session.'
        self.query_one('#preview-state', Static).update(text)
        running = self.workspace.busy
        self.query_one('#open-image', Button).disabled = latest is None or not Path('/usr/bin/open').is_file()
        self.query_one('#compare', Button).disabled = self.workspace.previous is None or running
        self.query_one('#export-image',Button).disabled=latest is None or running
        self.query_one('#export-sheet',Button).disabled=self.workspace.comparison_latest is None or running
        self.query_one('#cancel-preview').display = running
        self.query_one('#cancel-preview',Button).label='Cancel export' if self.workspace.operation=='export' else 'Cancel capture' if self.workspace.operation=='capture' else 'Cancel framing set' if self.workspace.operation=='comparison' else 'Cancel preview'

    def view(self):
        view = self.draft()
        view.validate()
        return view

    def resource_sections(self,*,attempt=True):
        sections=['On-demand evidence from a bounded finite diagnostic run; no provider, install, service or desktop action. Paths can be private; inspect before sharing.']
        if attempt:sections.append(safe('Last attempt: '+self.workspace.last_outcome+('\n'+self.workspace.last_error if self.workspace.last_error else '')))
        if self.workspace.capabilities:sections+=self.workspace.capabilities.sections()
        if self.workspace.last_resources:sections+=self.workspace.last_resources.sections()
        return sections

    def resource_report(self):
        self.push_screen(ReportScreen('Resource and binary diagnostics',self.resource_sections()))

    def show_health(self):
        sections = [f'{issue.severity.upper()} — {issue.field}: {issue.message}' for issue in self.current_issues()]
        sections.append('Read-only configuration/path checks. Actual output writes, PNG support and texture lookup are tested by Preview, not guaranteed by these checks.')
        sections.append('Last render attempt: ' + self.workspace.last_outcome +
                        ('\n' + self.workspace.last_error if self.workspace.last_error else ''))
        latest = self.workspace.latest
        if latest:
            sections.append('Latest successful scene: ' + latest.view.summary() + '\nRenderer: ' + str(latest.renderer) + '\nCompleted UTC: ' + latest.completed_utc)
            if latest.diagnostics:
                sections.append('Renderer diagnostics (bounded tail, not automatically classified):\n' + latest.diagnostics)
        if self.workspace.capabilities or self.workspace.last_resources:sections+=self.resource_sections(attempt=False)
        self.push_screen(ReportScreen('Configuration health', sections))

    def status(self, message):
        self.query_one('#status', Static).update(message)

    def on_button_pressed(self, event: Button.Pressed):
        action = event.button.id
        if action == 'load':
            self.capture_edit()
            self.push_screen(OpenView(str(self.document.source or self.root / 'dev' / 'earth-view'), self.history.dirty), self.load)
        elif action == 'moon-scales':
            view=self.draft()
            if not view.uses_system() or self.workspace.busy:self.status('Individual scales are available in an idle system-space draft.');return
            try:self.push_screen(MoonScalesScreen(view.target,view.satellite_scale,view.moon_scales),self.use_moon_scales)
            except ValueError as exc:self.status('Cannot edit moon overrides: '+str(exc))
        elif action=='selected-scene':
            if self.workspace.busy:self.status('Wait for the current preview/capture before inspecting selection.');return
            self.capture_edit();self.push_screen(SelectedSceneScreen(self.root,self.history.dirty),self.open_selected_native)
        elif action == 'handoff':
            if self.workspace.busy:self.status('Wait for the current preview/capture before reviewing a handoff.');return
            self.capture_edit()
            self.push_screen(HandoffScreen(self.root,self.document.source,self.query_one('#renderer',Input).value,self.history.dirty,on_selection=self.selection_finished),self.handoff_finished)
        elif action == 'edit-native':
            self.push_screen(NativePatchPath(str(self.root/'config/xp.conf')),self.open_native_values)
        elif action == 'inspect-native':
            self.push_screen(OpenView(str(self.document.source or self.root/'config/xp.conf'),inspection=True),self.inspect_source)
        elif action in ('library','stock'):
            self.capture_edit()
            stock=action=='stock'
            self.push_screen(SceneLibrary(STOCK_LIBRARY if stock else self.root/'config'/'scenes',self.history.dirty,stock=stock),self.load)
        elif action == 'undo':
            self.action_undo()
        elif action == 'redo':
            self.action_redo()
        elif action == 'review':
            self.push_screen(ReportScreen('Review unsaved scene changes', self.change_review()))
        elif action == 'capture-observations':
            products=self.draft().uses_observations()
            if products:
                source=self.query_one('#capture-root',Input).value;config=self.query_one('#capture-config',Input).value
                self.push_screen(ConfirmCapture(source,config,', '.join(products)+' observations'),lambda ok:self.start_observations(ok,source,config,products))
            else:self.status('Observation capture is available only for selected Earth Now layers.')
        elif action == 'capture-cloud':
            if self.draft().uses_capture():
                source=self.query_one('#capture-root',Input).value
                config=self.query_one('#capture-config',Input).value
                self.push_screen(ConfirmCapture(source,config),lambda ok:self.start_capture(ok,source,config))
            else:self.status('Existing-product capture is available only for Now scenes.')
        elif action=='help':self.action_help()
        elif action=='recovery':
            if self.recovery:self.push_screen(RecoveryScreen(self.recovery.store),self.restore_recovery)
        elif action == 'health':
            self.show_health()
        elif action=='framing-sheet':
            try:
                review=comparison_plan(self.view());renderer=self.query_one('#renderer',Input).value
                self.push_screen(ComparisonReview(review),lambda confirmed:self.start_comparison(confirmed,review,renderer))
            except ValueError as exc:self.status(str(exc))
        elif action=='open-sheet':
            if self.workspace.comparison_latest:open_image(self.workspace.comparison_latest.index)
        elif action in ('export-image','export-sheet'):
            kind='preview' if action=='export-image' else 'sheet'
            snapshot=self.workspace.latest if kind=='preview' else self.workspace.comparison_latest
            if snapshot is not None and not self.workspace.busy:
                description=(snapshot.view.summary()+'\nRender completed: '+snapshot.completed_utc) if kind=='preview' else ('Three recorded framing snapshots; epoch '+snapshot.plan.epoch)
                destination=self.root/'dev'/('export-'+kind+'-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
                self.push_screen(RenderExport(kind,description,str(destination)),lambda path:self.start_export(kind,snapshot,path))
        elif action == 'compare':
            if self.workspace.previous and self.workspace.latest:
                self.push_screen(ReportScreen('Before / after — two successful renders',
                    ['Open either snapshot deliberately. Different cameras/times are described below; this is not an aligned pixel-difference tool.'],
                    [('before', self.workspace.previous), ('after', self.workspace.latest)]))
        elif action == 'cancel-preview':
            if self.preview_job is not None:
                self.preview_job.cancel()
        elif action in ('preview','resources'):
            try:
                view = self.view()
                renderer = self.query_one('#renderer', Input).value
                self.preview_job = self.render(view, renderer,diagnostic=action=='resources')
            except ValueError as exc:
                self.status(str(exc))
        elif action == 'open-image':
            if self.workspace.image:
                open_image(self.workspace.image)
        elif action in ('save','save-continue'):
            try:
                view = self.view()
                renderer = self.query_one('#renderer', Input).value
                destination = self.query_one('#destination', Input).value
                self.push_screen(ConfirmSave(destination, self.change_review()),
                                 lambda confirmed: self.run_worker(self.save(confirmed, destination, view, renderer,keep_open=action=='save-continue')))
            except ValueError as exc:
                self.status(str(exc))
        elif action == 'cancel':
            self.run_worker(self.action_cancel())

    def use_moon_scales(self,value):
        if value is None:self.status('Moon override edits cancelled; draft unchanged.');return
        if value==self.moon_scales:self.status('Moon overrides unchanged; draft and source files unchanged.');return
        self.moon_scales=value;self.capture_edit()
        self.status('Moon overrides updated in draft only. Preview and Save remain explicit; source files unchanged.')

    def open_selected_native(self,source):
        if source is None:self.status('Selection inspection closed. Draft, source and selected-for-next-start choice unchanged.');return
        self.load(source)

    def selection_finished(self,label):
        self.selection_label=label

    def handoff_finished(self,result):
        message,label=result
        if label is not None:self.selection_label=label
        self.status(message or 'Handoff review closed. Source and draft unchanged; nothing activated.')

    def open_native_values(self,source):
        if source is None:self.status('Native editing cancelled. Source and draft unchanged.');return
        try:
            document=NativePatch.load(source)
            self.push_screen(NativePatchScreen(document),self.native_values_finished)
        except (ValueError,OSError) as exc:self.status('Native editing unavailable: '+str(exc)+' Source and draft unchanged.')

    def native_values_finished(self,target):
        self.status('Native edit cancelled. Source and draft unchanged.' if target is None else f'Native .conf copy saved to {target}. Source, companion definitions and current draft unchanged; no preview or Apply.')

    def inspect_source(self,source):
        if source is None:
            self.status('Inspection cancelled. Source and draft unchanged.');return
        try:
            review=inspect_native(source)
            self.push_screen(NativeReviewScreen(review,str(self.root/'config/native-snapshot')),lambda destination:self.copy_native_snapshot(review,destination))
        except (ValueError,OSError) as exc:self.status('Cannot inspect native files: '+str(exc))

    def copy_native_snapshot(self,review,destination):
        if destination is None:
            self.status('Inspection closed. Source and draft unchanged.');return
        try:
            target=copy_unchanged(review,destination)
            self.status(f'Original snapshot bytes copied to {target}. Open its copied .conf file if needed. Current draft/source unchanged; no Apply.')
        except (ValueError,OSError) as exc:self.status('Snapshot not copied: '+str(exc))

    def start_capture(self,confirmed,source,config):
        if not confirmed:
            self.status('Capture cancelled. No source data was read.')
        elif not self.draft().uses_capture():
            self.status('Capture is inactive for fixed UTC.')
        else:self.preview_job=self.capture_cloud(source,config)

    def start_observations(self,confirmed,source,config,products):
        if not confirmed:self.status('Capture cancelled. No source data was read.')
        elif not self.draft().uses_observations():self.status('Observations are inactive outside Earth Now scenes.')
        else:self.preview_job=self.capture_cloud(source,config,products)

    @work(exclusive=True,group='preview')
    async def capture_cloud(self,source,config,products=None):
        for field in ('preview','resources','save','save-continue','recovery','framing-sheet','open-sheet','load','library','stock','compare','capture-cloud','capture-observations','inspect-native','edit-native','handoff','selected-scene','moon-scales'):
            self.query_one('#'+field,Button).disabled=True
        self.query_one('#cancel-preview',Button).label='Cancel capture'
        self.query_one('#cancel-preview').display=True
        self.status('Capturing existing saved observation bytes… no provider request or refresh.' if products else 'Capturing existing saved cloud bytes… no provider request or refresh.')
        try:
            if products:
                frozen=await self.workspace.capture_observations(str(Path(source).expanduser()),config,products)
                self.observations_id=frozen.identity
            else:
                frozen=await self.workspace.capture_cloud(str(Path(source).expanduser()),config)
                self.capture_id=frozen.identity
            self.capture_edit()
            self.status(('Frozen '+', '.join(products)+' observations ready.' if products else 'Frozen cloud capture ready.')+' Review provenance before saving; original data is unchanged.')
        except asyncio.CancelledError:
            if not self.leaving:self.status('Capture cancelled. Previous capture and preview retained.')
        except (ValueError,OSError) as exc:
            if not self.leaving:self.status('Capture unavailable: '+str(exc)+' Previous capture and preview retained.')
        finally:
            if not self.leaving:
                for field in ('preview','resources','save','save-continue','recovery','framing-sheet','open-sheet','load','library','stock','capture-cloud','capture-observations','inspect-native','edit-native','handoff','selected-scene','moon-scales'):self.query_one('#'+field,Button).disabled=False
                self.update_controls()

    @work(exclusive=True, group='preview')
    async def render(self, view, renderer,diagnostic=False):
        for field in ('preview', 'resources', 'save', 'save-continue', 'recovery', 'framing-sheet', 'open-sheet', 'load', 'library', 'stock', 'compare', 'capture-cloud', 'capture-observations', 'inspect-native','edit-native','handoff','selected-scene','moon-scales'):
            self.query_one('#' + field, Button).disabled = True
        self.query_one('#cancel-preview').display = True
        self.status('Rendering one finite image… Ctrl-C or Cancel preview cancels work; Ctrl-D/Ctrl-Q requests exit.')
        try:
            image = await self.workspace.preview(view, renderer, config_bytes=self.document.config,**({'diagnostic':True} if diagnostic else {}))
            self.status(f'Preview ready: {view.summary()}.\n{image}')
        except asyncio.CancelledError:
            if not self.leaving:
                self.status('Preview cancelled. ' + ('Last successful preview retained.' if self.workspace.latest else 'No successful preview is available yet.'))
        except (ValueError, OSError) as exc:
            self.status(str(exc))
        finally:
            if diagnostic and self.workspace.capabilities is not None:
                try:store_binary_evidence(self.root,self.workspace.capabilities)
                except (OSError,ValueError) as exc:self.status('Diagnostic evidence remains in this session; could not save support cache: '+str(exc))
            if not self.leaving:
                for field in ('preview', 'resources', 'save', 'save-continue', 'recovery', 'framing-sheet', 'open-sheet', 'load', 'library', 'stock', 'capture-cloud', 'capture-observations', 'inspect-native','edit-native','handoff','selected-scene','moon-scales'):
                    self.query_one('#' + field, Button).disabled = False
                self.update_preview_state()
                if diagnostic and self.workspace.last_outcome!='cancelled' and not self.exit_prompting:self.resource_report()

    def start_export(self,kind,snapshot,destination):
        if destination is None:self.status('Export cancelled before writing. Prior snapshots and files unchanged.')
        else:self.preview_job=self.export_render(kind,snapshot,destination)

    @work(exclusive=True,group='preview')
    async def export_render(self,kind,snapshot,destination):
        fields=('preview','resources','framing-sheet','export-image','export-sheet','load','library','stock','save','save-continue','capture-cloud','capture-observations','handoff')
        for field in fields:self.query_one('#'+field,Button).disabled=True
        self.query_one('#cancel-preview').display=True;self.query_one('#cancel-preview',Button).label='Cancel export'
        self.status('Preparing a durable copy of the retained snapshot… Existing destinations will not be overwritten.')
        try:
            path=await export_snapshot(self.workspace,kind,snapshot,destination)
            self.status('Durable render exported to '+str(path)+'. Draft, native scenes and desktop selection unchanged.')
        except asyncio.CancelledError:
            if not self.leaving:self.status('Export cancelled; check the chosen destination before retrying. Prior snapshots and native files retained.')
        except (OSError,ValueError) as exc:self.status('Cannot export retained render: '+str(exc))
        finally:
            if not self.leaving:
                for field in fields:self.query_one('#'+field,Button).disabled=False
                self.update_preview_state()

    def start_comparison(self,confirmed,review,renderer):
        if confirmed:self.preview_job=self.render_comparison(review,renderer)
        else:self.status('Framing set cancelled before rendering; draft and prior previews unchanged.')

    @work(exclusive=True,group='preview')
    async def render_comparison(self,review,renderer):
        fields=('preview','resources','save','save-continue','recovery','framing-sheet','open-sheet','load','library','stock','compare','capture-cloud','capture-observations','inspect-native','edit-native','handoff','selected-scene','moon-scales')
        for field in fields:self.query_one('#'+field,Button).disabled=True
        self.query_one('#cancel-preview',Button).label='Cancel framing set';self.query_one('#cancel-preview',Button).display=True
        try:
            result=await render_set(self.workspace,review,renderer,config_bytes=self.document.config,progress=lambda index,total:self.status(f'Rendering framing snapshot {index}/{total}… Ctrl-C cancels; second Ctrl-C exits.'))
            self.status(f'Three framing snapshots ready at {review.epoch}. Open framing sheet explicitly. Draft, ordinary previews and desktop unchanged. Temporary sheet: {result.index}')
        except asyncio.CancelledError:
            if not self.leaving:self.status('Framing set cancelled. Prior complete sheet, previews and draft retained.')
        except (ValueError,OSError) as exc:
            if not self.leaving:self.status(str(exc))
        finally:
            if not self.leaving:
                for field in fields:self.query_one('#'+field,Button).disabled=False
                self.update_controls();self.update_preview_state()

    async def save(self, confirmed, destination, view, renderer,*,keep_open=False):
        if not confirmed:
            self.status('Save cancelled. Nothing was written.')
            return
        try:
            self.saved = (save_named if Path(destination).suffix.lower()=='.conf' else save_view)(destination,view,renderer,config_bytes=self.document.config,capture=self.workspace.capture_for(view),observations=self.workspace.observations_for(view))
            if keep_open:
                try:document=open_view(self.saved)
                except (ValueError,OSError) as exc:
                    self.status(f'Copy saved to {self.saved}, but reopening it failed: {exc}. Draft and undo retained; inspect the copy before continuing.')
                    return
                self.document=document
                self.history.record(self.raw_fields());self.history.mark_saved()
                if self.recovery:await self.recovery.discard_current()
                self.query_one('#view-source',Static).update(self.source_description())
                self.query_one('#destination',Input).value=self.copy_destination()
                self.update_controls();self.update_preview_state()
                self.status(f'New copy saved to {self.saved}. Continue editing; undo and captures remain. Selection and running desktop unchanged.')
            else:
                if self.recovery:await self.recovery.discard_current()
                self.exit(('saved',str(self.saved),self.selection_label) if self.selection_label is not None else ('saved',str(self.saved)))
        except (ValueError, OSError) as exc:
            self.status(str(exc))

    def action_help(self):
        if isinstance(self.screen,StudioHelp):self.screen.action_back()
        else:self.push_screen(StudioHelp())

    async def action_cancel(self):
        if self.exit_prompting:return
        if self.history is not None:
            self.history.record(self.raw_fields())
            editable_modal=any(isinstance(screen,ModalScreen) and bool(list(screen.query(Input))+list(screen.query(TextArea))) for screen in self.screen_stack)
            if self.history.dirty or editable_modal:
                self.exit_prompting=True
                if self.preview_job is not None:self.preview_job.cancel()
                await self.workspace.stop()
                self.push_screen(ConfirmDiscard(self.saved is not None,self.recovery is not None,editable_modal),self.discard_finished)
                return
        if self.recovery:await self.recovery.discard_current()
        await self.finish_exit()

    def discard_finished(self,discard):
        self.exit_prompting=False
        if discard=='keep':self.run_worker(self.keep_recovery_exit())
        elif discard:self.run_worker(self.discard_exit())
        else:self.status('Continue editing. Unsaved draft and saved copies retained.')

    async def keep_recovery_exit(self):
        if self.recovery is None:return
        if not await self.recovery.flush():
            self.status('Latest draft could not be checkpointed. Continue editing or save a new native copy; earlier recovery retained.');return
        await self.finish_exit('draft')

    async def discard_exit(self):
        if self.recovery:await self.recovery.discard_current()
        await self.finish_exit()

    def action_request_exit(self):
        if not self.exit_prompting and not self.leaving:self.run_worker(self.action_cancel())

    def action_interrupt(self):
        # Key dispatch must return immediately: awaiting TERM cleanup here would
        # prevent the next Ctrl-C from reaching the emergency escalation path.
        active=self.workspace.busy or (self.preview_job is not None and self.preview_job.state.name in ('PENDING','RUNNING'))
        if active and not self.cancelling_operation and not self.leaving:
            self.cancelling_operation=True
            if self.preview_job is not None:self.preview_job.cancel()
            self.run_worker(self.cancel_active_operation())
        else:
            self.termination_signal=signal.SIGINT
            if self.cancelling_operation:self.workspace.kill_owned()
            self.run_worker(self.action_force_cancel())

    async def cancel_active_operation(self):
        try:
            await self.workspace.stop()
            if not self.leaving:self.status('Operation cancelled. Draft and last successful preview retained. Ctrl-C while idle exits; Ctrl-D/Ctrl-Q requests exit.')
        finally:self.cancelling_operation=False

    async def action_force_cancel(self):
        if self.leaving:
            self.workspace.kill_owned()
            self.exit(self.completed_result())
            return
        await self.finish_exit(emergency=True)

    def completed_result(self):
        if self.saved is not None:return ('kept',str(self.saved),self.selection_label) if self.selection_label is not None else ('kept',str(self.saved))
        return ('selected',self.selection_label) if self.selection_label is not None else ('cancelled',None)

    async def finish_exit(self,kind=None,emergency=False):
        self.leaving=True
        if self.preview_job is not None:self.preview_job.cancel()
        if self.recovery:
            if emergency:
                self.recovery_notice=('Completed recovery checkpoints retained; latest edits may be absent. Inspect Recovery drafts on next entry.' if self.recovery.last_complete else 'No completed checkpoint known for this draft; recent unsaved edits may be lost.')
            await self.recovery.stop()
        await self.workspace.stop()
        if kind=='draft' and self.recovery and self.recovery.last_complete:
            path=self.recovery.store.path/self.recovery.last_complete[0]
            self.exit(('draft',str(path),self.selection_label) if self.selection_label is not None else ('draft',str(path)))
        else:self.exit(self.completed_result())

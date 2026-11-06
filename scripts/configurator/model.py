"""Constrained native scene model; definitions are data, never sourced."""
from dataclasses import dataclass, replace, field
from datetime import datetime, timezone, timedelta
import math
import hashlib
from .cloud_capture import FrozenCloud, IMAGE_FILE, META_FILE
from .observation_capture import FrozenObservations,PRODUCTS as OBS_PRODUCTS,names as observation_names
from .astronomy_capture import FrozenAstronomy,FILES as ASTRONOMY_FILES
from .geometry import DEFAULT_GEOMETRY,LEGACY_GEOMETRY,geometry
from .geography import COLORS, PLACE_FILE, ROUTE_FILE, HEADERS, validate_rows, read_rows
from pathlib import Path
import re
import shlex

SAMPLE = Path(__file__).with_name('samples') / 'earth.conf'
MAP_PROJECTIONS = ('rectangular', 'orthographic')
PROJECTIONS = (*MAP_PROJECTIONS, 'space')
PLANET_MAPS={
    'moon':'maps/solarsystem/03-01-moon/moon-4k.png',
    'mercury':'maps/solarsystem/01-00-mercury/mercury.jpg',
    'venus':'maps/solarsystem/02-00-venus/venussurface__praesepe.jpg',
    'mars':'maps/solarsystem/04-00-mars/Mars_2k-050104.png',
    'jupiter':'maps/solarsystem/05-00-jupiter/Jupiter.png',
    'saturn':'maps/solarsystem/06-00-saturn/th_saturn.png',
    'uranus':'maps/solarsystem/07-00-uranus/UranusJVV.png',
    'neptune':'maps/solarsystem/08-00-neptune/neptune2k.jpg',
    'phobos':'maps/solarsystem/04-01-phobos/2kPhobosMap.png',
    'deimos':'maps/solarsystem/04-02-deimos/2kDeimos.png',
    'io':'maps/solarsystem/05-01-io/Io.png',
    'europa':'maps/solarsystem/05-02-europa/europa1_out.jpg',
    'ganymede':'maps/solarsystem/05-03-ganymede/ganymede.jpg',
    'callisto':'maps/solarsystem/05-04-callisto/callisto.jpg',
    'mimas':'maps/solarsystem/06-01-mimas/mimas2kalb.jpg',
    'enceladus':'maps/solarsystem/06-02-enceladus/Enceladus.png',
    'tethys':'maps/solarsystem/06-03-tethys/tethys4kalb.jpg',
    'dione':'maps/solarsystem/06-04-dione/JVV_Dione.png',
    'rhea':'maps/solarsystem/06-05-rhea/rhea4kalb.jpg',
    'titan':'maps/solarsystem/06-06-titan/Titan.png',
    'hyperion':'maps/solarsystem/06-07-hyperion/JVV_Hyperion.png',
    'iapetus':'maps/solarsystem/06-08-iapetus/iapetus4kalb.jpg',
    'phoebe':'maps/solarsystem/06-09-phoebe/JVV_Phoebe.png',
    'miranda':'maps/solarsystem/07-01-miranda/miranda3.jpg',
    'pluto':'maps/solarsystem/09-00-pluto/JVV.Pluto.png',
    'charon':'maps/solarsystem/09-01-charon/JVV.Charon.png',
}
TARGETS=('earth',*PLANET_MAPS)
OBSERVERS=('geographic',*TARGETS,'sun','opposite_sun')
EAST_POSITIVE=('earth','moon','venus','uranus','miranda','pluto','charon')
MOON_PARENTS={'moon':'earth','phobos':'mars','deimos':'mars',
              **dict.fromkeys(('io','europa','ganymede','callisto'),'jupiter'),
              **dict.fromkeys(('mimas','enceladus','tethys','dione','rhea','titan','hyperion','iapetus','phoebe'),'saturn'),
              'miranda':'uranus','charon':'pluto'}
SYSTEMS={parent:tuple(body for body,primary in MOON_PARENTS.items() if primary==parent)
         for parent in ('mars','jupiter','saturn','uranus','pluto')}
# Longest configured moon periods in reviewed Xplanet 1.3.1 (days).
SYSTEM_PERIOD_DAYS={'mars':1.2624407,'jupiter':16.6890184,'saturn':550.48,'uranus':1.41347925,'pluto':6.38723}
MOON_SCALE_BODIES=tuple(body for members in SYSTEMS.values() for body in members)
HEADER = '# Xplanet configurator scene v16; saving does not apply it.'
V15_HEADER = '# Xplanet configurator scene v15; saving does not apply it.'
V14_HEADER = '# Xplanet configurator scene v14; saving does not apply it.'
V13_HEADER = '# Xplanet configurator scene v13; saving does not apply it.'
V12_HEADER = '# Xplanet configurator scene v12; saving does not apply it.'
V11_HEADER = '# Xplanet configurator scene v11; saving does not apply it.'
V10_HEADER = '# Xplanet configurator scene v10; saving does not apply it.'
V9_HEADER = '# Xplanet configurator scene v9; saving does not apply it.'
V8_HEADER = '# Xplanet configurator scene v8; saving does not apply it.'
V7_HEADER = '# Xplanet configurator scene v7; saving does not apply it.'
V6_HEADER = '# Xplanet configurator scene v6; saving does not apply it.'
V5_HEADER = '# Xplanet configurator scene v5; saving does not apply it.'
V4_HEADER = '# Xplanet configurator scene v4; saving does not apply it.'
V3_HEADER = '# Xplanet configurator scene v3; saving does not apply it.'
V2_HEADER = '# Xplanet configurator scene v2; saving does not apply it.'
ROOT = Path(__file__).resolve().parents[2]
MAP_FAMILIES = ('stock', 'world', 'world.topo', 'world.topo.bathy')
MONTHS = tuple(f'{month:02d}' for month in range(1, 13))
NIGHT_MAPS = ('stock', 'lights2002')
GRIDS = ('off', '30', '15', '10')
LAYER_ASSETS = {
    'relief': 'maps/bump/gebco_08_rev_elev_21600x10800.png',
    'specular': 'maps/specular/specular.png',
    'clouds': 'maps/clouds/clouds_26Aug2011_2048.jpeg',
}
SCENE_HEADERS={HEADER:16,V15_HEADER:15,V14_HEADER:14,V13_HEADER:13,V12_HEADER:12,V11_HEADER:11,V10_HEADER:10,V9_HEADER:9,V8_HEADER:8,V7_HEADER:7,V6_HEADER:6,V5_HEADER:5,V4_HEADER:4,V3_HEADER:3,V2_HEADER:2}

ORIGIN_FILE='camera.origin'
LUNAR_BODY=('\n# Xplanet configurator lunar orbital observer v15.\n[moon]\nmap='+PLANET_MAPS['moon']+'\ngrid=false\n').encode()

LOCAL_REFERENCES=(('marker_file',PLACE_FILE),('arc_file',ROUTE_FILE),('cloud_map',IMAGE_FILE),
                  *((key,name) for product in OBS_PRODUCTS for key,name in
                    (('marker_file',observation_names(product)[0]),('arc_file',observation_names(product)[1]))),
                  ('satellite_file',ASTRONOMY_FILES['norad'][0]),('marker_file',ASTRONOMY_FILES['eclipse'][0]),('arc_file',ASTRONOMY_FILES['eclipse'][1]))

LEGACY_HEADER = '# Earth sample from the configurator; saving does not apply it.'


def scene_prefix(prefix):
    if prefix and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}\.',prefix):
        raise ValueError('Use a scene name of 1–48 ASCII letters, digits, underscores or hyphens.')
    return prefix


def body_names(body,prefix):
    scene_prefix(prefix)
    if prefix:
        for key,name in LOCAL_REFERENCES:
            body=body.replace(f'{key}={name}\n'.encode(),f'{key}={prefix}{name}\n'.encode())
    return body


def number(value):
    """Readable float round-trip; do not round saved/reopened camera values."""
    text = repr(float(value))
    return text[:-2] if text.endswith('.0') else text


def utc_date(value):
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value):
        raise ValueError('Use UTC YYYY-MM-DDTHH:MM:SSZ, for example 2000-01-01T12:00:00Z.')
    try:
        result = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError('The fixed UTC date/time is not a valid calendar instant.') from exc
    if not 1800 <= result.year <= 2200:
        raise ValueError('This studio slice supports fixed UTC years 1800–2200; astronomical accuracy is not certified.')
    return result


@dataclass(frozen=True)
class Issue:
    severity: str
    field: str
    message: str


NUMERIC_FIELDS = {'orbit_latitude':('Lunar observer latitude',-90,90),'orbit_longitude':('Lunar observer longitude',-180,180),'orbit_range':('Lunar observer range',1.1,100),'frame_x':('Frame centre X percent',0,100),'frame_y':('Frame centre Y percent',0,100),'orbit_width': ('Orbital path width', 1, 3), 'satellite_scale': ('Satellite visual enlargement', 1, 10), 'latitude': ('Latitude', -90, 90), 'longitude': ('Longitude', -180, 180),
                  'radius': ('Radius', .1, 100), 'fov': ('Field of view', .1, 179), 'twilight': ('Twilight', 0, 90),
                  'place_size': ('Place font size', 10, 24), 'route_width': ('Route width', 1, 5),
                  'relief_scale': ('Relief exaggeration', .1, 5), 'relief_shade': ('Relief shadow brightness', 0, 100),
                  'planet_shade': ('Planetary shadow brightness', 0, 100), 'solar_hour': ('Local solar hour', 0, 24), 'distance': ('Observer distance', 1.01, 1000000),
                  'rotation': ('Rotation', -180, 180), 'cloud_gamma': ('Cloud gamma', .1, 5), 'cloud_threshold': ('Cloud threshold', 0, 255)}


def moon_scale_number(value):
    text=str(value)
    if len(text)>64 or not re.fullmatch(r'[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',text):
        raise ValueError('Use a literal moon scale from 1 to 10; blank uses the shared scale.')
    result=float(text);_,low,high=NUMERIC_FIELDS['satellite_scale']
    if not math.isfinite(result) or not low<=result<=high:raise ValueError('Moon overrides must be finite scales from 1 to 10; zero does not hide a body.')
    return result


def parse_moon_scales(text):
    if not isinstance(text,str) or len(text)>1024:raise ValueError('Moon overrides must be bounded native metadata (up to 1024 characters).')
    result={}
    for entry in text.split(',') if text else ():
        name,separator,value=entry.partition('=')
        if not separator or name not in MOON_SCALE_BODIES or name in result:raise ValueError('Use each supported system moon at most once in the override table.')
        result[name]=moon_scale_number(value)
    return result


def encode_moon_scales(values):
    if not isinstance(values,dict) or not set(values)<=set(MOON_SCALE_BODIES):raise ValueError('Unknown moon in override table.')
    return ','.join(name+'='+number(moon_scale_number(value)) for name,value in sorted(values.items()) if value!='')


def require_valid(issues):
    blocking = [issue.message for issue in issues if issue.severity == 'blocking']
    if blocking:
        raise ValueError('\n'.join(blocking))


def choice_rules():
    choices = [('camera_mode',('centre','lunar_orbit'),'Choose body centre or lunar orbital camera.'),('orbit_paths', ('off','on'), 'Choose orbital guides off or on.'),
               ('orbit_color', COLORS, 'Choose a supported orbital path color.'),
               ('composition', ('target','system'), 'Choose target appearance or bundled system appearance.'),
               ('target', TARGETS, 'Choose a supported planet, dwarf planet or moon with a bundled texture.'),
               ('longitude_mode', ('longitude','solar'), 'Choose longitude or local solar hour.'),
               ('north', ('body','galactic','orbit'), 'Choose body, galactic or orbital north.'),
               ('projection', PROJECTIONS, 'Choose rectangular, orthographic or space mode.'),
               ('observer', OBSERVERS, 'Choose a supported observer.'),
               ('framing', ('radius', 'fov'), 'Choose radius or FOV framing.'),
               ('time_mode', ('now', 'fixed'), 'Choose Now or fixed UTC.'),
               ('map_family', MAP_FAMILIES, 'Choose stock or a bundled seasonal map family.'),
               ('month', MONTHS, 'Choose a month from 01 to 12.'),
               ('night', NIGHT_MAPS, 'Choose stock night imagery or bundled 2002 lights.'),
               ('grid', GRIDS, 'Choose off or a 30, 15 or 10 degree grid.'),
               ('label', ('off', 'utc'), 'Choose no label or a UTC scene label.'),
               ('places', ('off','on'), 'Choose places off or on.'),
               ('routes', ('off','on'), 'Choose routes off or on.'),
               ('place_color', COLORS, 'Choose a supported place color.'),
               ('route_color', COLORS, 'Choose a supported route color.'),
               ('relief', ('off','gebco'), 'Choose relief off or bundled GEBCO.'),
               ('relief_shadow', ('night','shade'), 'Choose relief shadows from night imagery or shaded day map.'),
               ('specular', ('off','bundled'), 'Choose specular reflection off or bundled.'),
               ('clouds', ('off','snapshot2011','captured'), 'Choose clouds off, the bundled 2011 image or an explicit frozen TotalMarker capture.')]
    choices.extend((p+'_layer',('off','captured'),'Choose observations off or frozen capture.') for p in (*OBS_PRODUCTS,*ASTRONOMY_FILES))
    return choices


@dataclass(frozen=True)
class View:
    latitude: float = 0
    longitude: float = 0
    projection: str = 'rectangular'
    observer: str = 'geographic'
    framing: str = 'radius'
    radius: float = 45
    fov: float = 30
    time_mode: str = 'now'
    utc: str = '2000-01-01T12:00:00Z'
    map_family: str = 'stock'
    month: str = '01'
    night: str = 'stock'
    twilight: float = 6
    grid: str = 'off'
    label: str = 'off'
    places: str = 'off'
    places_text: str = ''
    place_color: str = 'yellow'
    place_size: float = 14
    routes: str = 'off'
    routes_text: str = ''
    route_color: str = 'cyan'
    route_width: float = 2
    relief: str = 'off'
    relief_scale: float = 1
    relief_shadow: str = 'night'
    relief_shade: float = 30
    specular: str = 'off'
    clouds: str = 'off'
    cloud_gamma: float = 1
    cloud_threshold: float = 90
    capture_id: str = ''
    longitude_mode: str = 'longitude'
    solar_hour: float = 12
    distance: float = 1000
    north: str = 'body'
    rotation: float = 0
    target: str = 'earth'
    planet_shade: float = 30
    quake_layer: str = 'off'
    volcano_layer: str = 'off'
    storm_layer: str = 'off'
    observations_id: str = ''
    norad_layer: str = 'off'
    norad_id: str = ''
    eclipse_layer: str = 'off'
    eclipse_id: str = ''
    eclipse_window: str = ''
    composition: str = 'target'
    satellite_scale: float = 1
    orbit_paths: str = 'off'
    orbit_color: str = 'cyan'
    orbit_width: float = 1
    moon_scales: str = ''
    geometry: str = DEFAULT_GEOMETRY
    camera_mode: str = 'centre'
    orbit_latitude: float = 0
    orbit_longitude: float = 145
    orbit_range: float = 2
    frame_x: float = 50
    frame_y: float = 50

    @classmethod
    def from_fields(cls, fields):
        values = dict(fields)
        for field in NUMERIC_FIELDS:
            try:
                values[field] = float(values.get(field, getattr(cls(), field)))
            except (ValueError, TypeError):
                pass  # Keep the invalid draft text so health can explain it.
        return cls(**values)

    def active_fields(self):
        fields = {'geometry', 'projection', 'time_mode', 'map_family', 'night', 'twilight', 'grid', 'label'}
        fields |= {'places', 'routes', 'relief', 'specular', 'clouds'}
        if self.relief=='gebco':
            fields |= {'relief_scale','relief_shadow'}
            if self.relief_shadow=='shade':fields.add('relief_shade')
        if self.clouds=='snapshot2011' or self.uses_capture():fields |= {'cloud_gamma','cloud_threshold'}
        if self.uses_capture():fields.add('capture_id')
        if self.places == 'on':fields |= {'places_text','place_color','place_size'}
        if self.routes == 'on':fields |= {'routes_text','route_color','route_width'}
        if self.map_family != 'stock':
            fields.add('month')
        if self.projection == 'space':
            fields |= {'observer', 'framing', self.framing, 'north', 'rotation','frame_x','frame_y'}
            if self.observer=='moon':fields.add('camera_mode')
            if self.uses_lunar_camera():fields|={'orbit_latitude','orbit_longitude','orbit_range'}
        if self.projection != 'space' or self.observer == 'geographic':
            fields |= {'latitude', 'longitude_mode', 'solar_hour' if self.longitude_mode=='solar' else 'longitude'}
            if self.projection=='space':fields.add('distance')
        if self.time_mode == 'fixed':
            fields.add('utc')
        fields.add('target')
        if self.projection=='space' and self.target in SYSTEMS:
            fields.add('composition')
            if self.composition=='system':fields|={'satellite_scale','orbit_paths','moon_scales'}
            if self.uses_orbits():fields|={'orbit_color','orbit_width'}
        if self.target=='earth':
            fields|={p+'_layer' for p in (*OBS_PRODUCTS,*ASTRONOMY_FILES)}
            if self.uses_observations():fields.add('observations_id')
            for product in self.uses_astronomy():fields.add(product+'_id')
            if 'eclipse' in self.uses_astronomy():fields.add('eclipse_window')
        if self.target!='earth':fields.add('planet_shade')
        if self.target!='earth':
            fields-={'map_family','month','night','twilight','places','places_text','place_color','place_size',
                     'routes','routes_text','route_color','route_width','relief','relief_scale','relief_shadow','relief_shade',
                     'specular','clouds','cloud_gamma','cloud_threshold','capture_id'}
        return fields

    def issues(self):
        issues = []
        for product in ASTRONOMY_FILES:
            value=getattr(self,product+'_id')
            if not isinstance(value,str) or value and not re.fullmatch('[0-9a-f]{64}',value):issues.append(Issue('blocking',product+'_id','Invalid frozen astronomy identity.'))
        if self.eclipse_window:
            try:self.eclipse_bounds()
            except (ValueError,TypeError):issues.append(Issue('blocking','eclipse_window','Invalid frozen eclipse interval.'))
        if self.target=='earth' and self.norad_layer=='captured' and self.time_mode!='now':issues.append(Issue('info','norad_layer','NORAD is inactive outside Now; selection and captured bytes are retained.'))
        if self.target=='earth' and self.eclipse_layer=='captured' and 'eclipse' not in self.uses_astronomy():issues.append(Issue('info','eclipse_layer','Eclipse is inactive: choose Fixed UTC within captured central-path sample coverage; selection and bytes are retained.'))
        try:geometry(self.geometry)
        except ValueError as exc:issues.append(Issue('blocking','geometry',str(exc)))
        try:overrides=parse_moon_scales(self.moon_scales)
        except ValueError as exc:
            overrides={};issues.append(Issue('blocking','moon_scales',str(exc)))
        for field, allowed, message in choice_rules():
            if getattr(self, field) not in allowed:
                issues.append(Issue('blocking', field, message))
        for field, (label, low, high) in NUMERIC_FIELDS.items():
            value = getattr(self, field)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
                issues.append(Issue('blocking', field,
                                    f'{label} must be a finite number between {low:g} and {high:g}. '
                                    'Retained inactive settings must also be valid.'))
        for field in ('place_size','route_width','relief_shade','cloud_threshold','planet_shade','orbit_width'):
            value=getattr(self,field)
            if isinstance(value,(int,float)) and math.isfinite(value) and value!=int(value):
                issues.append(Issue('blocking',field,'Use a whole number for pixel sizes, cloud threshold and shadow percentage.'))
        for field,places in (('places_text',True),('routes_text',False)):
            try:
                count=validate_rows(getattr(self,field),places)
                if getattr(self,'places' if places else 'routes')=='on':
                    issues.append(Issue('info',field,f'{count} surface-coordinate rows enabled; back-side/overlapping labels may not be visible.'))
            except ValueError as exc:issues.append(Issue('blocking',field,str(exc)))
        if self.projection=='space' and self.observer==self.target:
            issues.append(Issue('blocking','observer','Observer and target must be different bodies. Choose a geographic viewpoint or another origin.'))
        if self.uses_lunar_camera():
            if self.time_mode!='fixed':issues.append(Issue('blocking','time_mode','Lunar orbital camera requires fixed UTC; a one-row origin file must not silently freeze a Now scene.'))
            issues.append(Issue('warning','camera_mode','Lunar orbital camera: range is lunar radii from the centre, not altitude. Spherical limb and static texture, no terrain or surface/event reconstruction; close views may clip or be occluded. Near-Sun Earth appears crescent/dark.'))
        if self.uses_orbits():
            issues.append(Issue('warning','orbit_paths','One nominal orbit per configured moon, sampled at 5° with the parent held at the scene epoch. These are illustrative paths, not physical event predictions or spacecraft trajectories.'))
            before,after=self.orbit_padding()
            issues.append(Issue('info','orbit_paths',f"Date-policy padding: {before} days before and {after} days after the scene time, conservatively including the renderer's extra sample. Orbital path centers do not follow visual moon enlargement."))
        if self.uses_system():
            issues.append(Issue('info','composition','Configured companions: '+', '.join(SYSTEMS[self.target])+'. Camera framing is unchanged; bodies can be off-screen, behind the observer or too small to distinguish. Other engine bodies remain eligible to render.'))
            issues.append(Issue('info','composition','Per-body hiding is unavailable: magnify=0 still plots a point in this engine. No visibility guarantee or auto-fit is provided.'))
            effective=[(body,overrides.get(body,self.satellite_scale)) for body in SYSTEMS[self.target]]
            enlarged=[(body,value) for body,value in effective if isinstance(value,(int,float)) and math.isfinite(value) and value!=1]
            if enlarged:
                scales=', '.join(body.title()+' '+number(value)+'×' for body,value in enlarged)
                issues.append(Issue('warning','moon_scales' if any(body in overrides for body in SYSTEMS[self.target]) else 'satellite_scale','Effective moon enlargement: '+scales+'. Positions/orbits are unchanged; apparent contacts, overlap and shadows are not a physical event prediction.'))
            if overrides:issues.append(Issue('info','moon_scales','Overrides replace the shared scale; blank restores inheritance. Other-family overrides are retained and inactive.'))
        if self.uses_system() and self.target=='uranus':
            issues.append(Issue('warning','target','Only Miranda has a bundled Uranian-moon map. Other Uranian moons can enter the frame without textures and produce missing-map warnings; no replacement maps or hiding are applied.'))
        if self.target in MOON_PARENTS and self.target!='moon':
            issues.append(Issue('warning','target',f'{self.target.title()} orbits {MOON_PARENTS[self.target].title()}. The renderer uses built-in satellite approximations and simplified body shape; no accuracy interval is certified for these views.'))
        if self.projection=='space' and self.observer in MOON_PARENTS and self.observer!='moon':
            issues.append(Issue('warning','observer',f'{self.observer.title()} origin uses a built-in satellite approximation, not an externally validated spacecraft or observer ephemeris.'))
        if self.target in ('pluto','charon'):
            issues.append(Issue('warning','target','Pluto/Charon use legacy bundled textures and renderer geometry, not a reconstruction of New Horizons observations.'))
        if self.target=='venus':
            issues.append(Issue('warning','target','Venus uses the bundled surface texture, not its optically visible cloud deck. Texture availability does not certify provenance, epoch or alignment.'))
        if self.target=='saturn':
            issues.append(Issue('info','target', 'Saturn rings are rendered internally in space mode; radius framing includes the outer rings. Projected maps omit the visible ring system, though ring shadows may affect the surface.' if self.projection=='space' else 'Projected Saturn shows the surface map, potentially with ring shadows. Choose space mode for the visible ring system.'))
        if self.target in ('jupiter','saturn','uranus','neptune'):
            issues.append(Issue('info','target','Giant-planet texture is static; surface appearance and moving atmospheric features are not reconstructed at the chosen time. Rings for other planets are not enabled.'))
        if self.target!='earth':
            issues.append(Issue('info','target',('Bundled system textures; ' if self.uses_system() else 'Bundled target texture only; ')+'Earth layers and annotations are retained but inactive. Geometry uses this renderer build; texture epoch, orientation and ephemeris accuracy are not certified. No external kernels or live data are loaded.'))
        if not isinstance(self.observations_id,str) or self.observations_id and not re.fullmatch('[0-9a-f]{64}',self.observations_id):
            issues.append(Issue('blocking','observations_id','Invalid frozen observation identity.'))
        if any(getattr(self,p+'_layer')=='captured' for p in OBS_PRODUCTS) and (self.target!='earth' or self.time_mode!='now'):
            issues.append(Issue('info','observations_id','Current observational markers/arcs and update labels are inactive outside Earth Now scenes; selections and bytes are retained.'))
        if not isinstance(self.capture_id,str) or (self.capture_id and not re.fullmatch('[0-9a-f]{64}',self.capture_id)):
            issues.append(Issue('blocking','capture_id','Invalid captured cloud identity.'))
        if self.target=='earth' and (self.clouds=='captured' and self.time_mode=='fixed'):
            issues.append(Issue('info','clouds','Current-data-derived clouds are inactive for fixed UTC. Choice and captured bytes are retained; no live update labels are included.'))
        if self.target=='earth' and (self.relief!='off' or self.specular!='off'):
            issues.append(Issue('warning','layers','Bundled relief/specular maps are high resolution and can require substantial decoding memory and time. Preview remains finite/cancellable; texture presence is not feature certification.'))
        if self.target=='earth' and (self.relief=='gebco'):
            issues.append(Issue('info','relief','Relief exaggeration affects shading, not camera altitude or certified terrain geometry; scale 0.1–5 is a studio range.'))
        if self.target=='earth' and (self.clouds=='snapshot2011'):
            issues.append(Issue('warning','clouds','Clouds are a bundled 26 August 2011 image, not current weather or observations at the chosen scene time. No provider refresh is performed.'))
            issues.append(Issue('info','clouds','Gamma changes cloud brightness and threshold hides dimmer pixels; a high threshold can make the layer invisible.'))
        if self.target=='earth' and (self.places=='on'):
            issues.append(Issue('info','places','Place labels depend on renderer font/glyph support; geographic surface degrees only, not pixel/sky positions.'))
        if self.target=='earth' and (self.routes=='on'):
            issues.append(Issue('info','routes','Routes are static great-circle surface arcs, not travel trajectories or eclipse predictions; identical endpoints draw no length and antipodal paths are ambiguous.'))
        if isinstance(self.twilight, (int, float)) and math.isfinite(self.twilight) and self.twilight != int(self.twilight):
            issues.append(Issue('blocking', 'twilight', 'Twilight must be a whole number of degrees (0–90).'))
        if self.target=='earth' and (self.night == 'lights2002'):
            issues.append(Issue('warning', 'night', 'Bundled city lights are a 2002 image, not observations at the scene time.'))
        if self.target=='earth' and (self.map_family != 'stock'):
            issues.append(Issue('info', 'map_family', 'Seasonal maps are 2004 monthly composites; month is selected independently of scene time.'))
        if self.label == 'utc':
            issues.append(Issue('info', 'label', 'UTC label describes scene geometry/time, not data freshness. Font support is renderer/build dependent.'))
        try:
            date=utc_date(self.utc)
            pluto_geometry=self.target in ('pluto','charon') or (self.projection=='space' and self.observer in ('pluto','charon'))
            if pluto_geometry:
                issues.append(Issue('warning','utc','Pluto/Charon fixed-time studio policy is 1800–2099, conservatively inside the built-in Pluto series window. This is an input guard, not an accuracy guarantee.'))
                if self.time_mode=='fixed' and date.year>=2100:
                    issues.append(Issue('blocking','utc','Pluto/Charon geometry requires fixed UTC before 2100 in this studio. Choose 1800–2099 or another target/viewpoint.'))
            if self.time_mode=='fixed' and self.uses_orbits():
                before,after=self.orbit_padding()
                lower=datetime(1800,1,1,tzinfo=timezone.utc);upper=datetime(2100 if pluto_geometry else 2201,1,1,tzinfo=timezone.utc)
                if date-timedelta(days=before)<lower or date+timedelta(days=after)>=upper:
                    issues.append(Issue('blocking','utc',f'Orbital path samples exceed the scene date policy. Choose UTC from {(lower+timedelta(days=before)).strftime("%Y-%m-%dT%H:%M:%SZ")} up to (excluding) {(upper-timedelta(days=after)).strftime("%Y-%m-%dT%H:%M:%SZ")}, or turn paths off.'))
        except (ValueError, TypeError) as exc:
            issues.append(Issue('blocking', 'utc', str(exc)))
        if self.time_mode == 'fixed':
            issues.append(Issue('warning', 'utc', 'Fixed UTC changes geometry, not the date of stock/bundled textures or observations; historical city lights are not reconstructed.'))
        else:
            issues.append(Issue('info', 'time_mode', 'Now samples the renderer clock for each finite image; a retained preview is not a live display.'))
        if self.projection == 'space' and self.observer == 'opposite_sun':
            issues.append(Issue('warning', 'observer', 'Sun/glare behind the target can produce a bright background in opposite-Sun views.'))
        if self.longitude_mode=='solar' and 'solar_hour' in self.active_fields():
            issues.append(Issue('info','solar_hour','Local solar hour selects longitude relative to the Sun; it is not a civil timezone.'))
        if self.projection=='space' and self.observer=='geographic':
            issues.append(Issue('info','distance','Range is distance from the target center in body radii for a geographic observer; radius/FOV controls image framing independently. Rotation is counterclockwise from selected north.'))
        issues.append(Issue('info', 'inactive', 'Inactive choices are retained and omitted from active renderer arguments.'))
        return issues

    def validate(self):
        require_valid(self.issues())

    def uses_lunar_camera(self):
        return self.projection=='space' and self.observer=='moon' and self.camera_mode=='lunar_orbit'

    def origin_data(self):
        self.validate()
        if not self.uses_lunar_camera():return None
        return (utc_date(self.utc).strftime('%Y%m%d.%H%M%S')+' '+number(self.orbit_range)+' '+number(self.orbit_latitude)+' '+number(self.orbit_longitude)+'\n').encode()

    def arguments(self, *, asset_prefix='', geometry_override=None):
        self.validate()
        scene_prefix(asset_prefix)
        dimensions=geometry(geometry_override or self.geometry)
        args = ['-body', self.target]
        if self.projection in MAP_PROJECTIONS:
            args += ['-projection', self.projection]
        if self.projection != 'space' or self.observer == 'geographic':
            args += ['-latitude', number(self.latitude)]
            args += ['-localtime', number(self.solar_hour)] if self.longitude_mode=='solar' else ['-longitude', number(self.longitude)]
            if self.projection=='space':args += ['-range',number(self.distance)]
        else:
            origin = '-sun' if self.observer == 'opposite_sun' else self.observer
            args += ['-origin', origin]
        if self.projection == 'space':
            args += ['-north',self.north,'-rotate',number(self.rotation)]
            args += ['-radius', number(self.radius)] if self.framing == 'radius' else ['-fov', number(self.fov)]
        if self.time_mode == 'fixed':
            args += ['-date', utc_date(self.utc).strftime('%Y%m%d.%H%M%S')]
        if self.label == 'utc':
            args += ['-gmtlabel']
        if self.uses_lunar_camera():args+=['-dynamic_origin',asset_prefix+ORIGIN_FILE]
        if self.projection=='space' and (self.frame_x,self.frame_y)!=(50,50):
            width,height=map(int,dimensions.split('x'));args+=['-center',f'+{round(width*self.frame_x/100)}+{round(height*self.frame_y/100)}']
        return args + ['-geometry', dimensions]

    def summary(self):
        observer = (f'geographic {number(self.latitude)}, {number(self.longitude)}'
                    if self.observer == 'geographic' else self.observer)
        framing = f'radius {number(self.radius)}%' if self.framing == 'radius' else f'FOV {number(self.fov)}°'
        camera = (f'{self.projection} map at {number(self.latitude)}, {number(self.longitude)}'
                  if self.projection != 'space' else f'space / {observer} / {framing}')
        clock = 'current scene time' if self.time_mode == 'now' else self.utc
        orientation=f'; {self.north} north; rotation {number(self.rotation)}°' if self.projection=='space' else ''
        solar=f'; local solar hour {number(self.solar_hour)} (longitude overridden)' if 'solar_hour' in self.active_fields() else ''
        distance=f'; range {number(self.distance)} body radii' if 'distance' in self.active_fields() else ''
        orbital=(f'; lunar orbital observer {number(self.orbit_latitude)}, {number(self.orbit_longitude)}; {number(self.orbit_range)} lunar radii from centre' if self.uses_lunar_camera() else '')
        centre=f'; centre {number(self.frame_x)}%, {number(self.frame_y)}%' if self.projection=='space' and (self.frame_x,self.frame_y)!=(50,50) else ''
        return f'{self.target.title()}: {camera}{solar}{distance}{orientation}{orbital}; {clock}; frame {self.geometry}{centre}; {self.appearance_summary()}'

    def uses_system(self):
        return self.composition=='system' and self.projection=='space' and self.target in SYSTEMS

    def system_scales(self):
        overrides=parse_moon_scales(self.moon_scales)
        return {body:overrides.get(body,self.satellite_scale) for body in SYSTEMS.get(self.target,())}

    def uses_orbits(self):
        return self.uses_system() and self.orbit_paths=='on'

    def orbit_padding(self):
        period=SYSTEM_PERIOD_DAYS[self.target]
        # addArc emits an extra segment past stop; retain whole-day margins.
        return math.ceil(period*.5),math.ceil(period*(.5+.5/36))

    def appearance_summary(self):
        if self.uses_system():
            scale=number(self.satellite_scale) if isinstance(self.satellite_scale,(int,float)) and math.isfinite(self.satellite_scale) else 'invalid'
            try:
                overrides=parse_moon_scales(self.moon_scales)
                selected=', '.join(body.title()+' '+number(overrides[body])+'×' for body in SYSTEMS[self.target] if body in overrides)
            except ValueError:selected='invalid override table'
            detail=('; overrides: '+selected) if selected else ''
            return f'{self.target.title()} system textures; shared moon scale {scale}×'+detail+f'; no visibility isolation or auto-fit; shadow {self.planet_shade}%'+(f'; illustrative orbits {self.orbit_color}, {self.orbit_width}px' if self.uses_orbits() else '')
        if self.target!='earth':return f'bundled {self.target.title()} texture; shadow {number(self.planet_shade)}%; grid {self.grid}; label {self.label}; Earth layers inactive'
        day = 'stock day' if self.map_family == 'stock' else f'{self.map_family} / month {self.month} (2004)'
        text=f'{day}; {self.night} night; twilight {self.twilight}°; grid {self.grid}; label {self.label}; places {self.places}; routes {self.routes}'
        layers=[f'{field}={getattr(self,field)}'+(' (inactive for fixed UTC)' if field=='clouds' and self.clouds=='captured' and self.time_mode=='fixed' else '') for field in ('relief','specular','clouds') if getattr(self,field)!='off']
        selected=[p for p in OBS_PRODUCTS if getattr(self,p+'_layer')=='captured']
        if selected:text+='; frozen observations '+', '.join(selected)+(' (inactive outside Now)' if self.time_mode!='now' else '')
        astronomy=[p for p in ASTRONOMY_FILES if getattr(self,p+'_layer')=='captured']
        if astronomy:text+='; astronomy '+', '.join(p+(' active' if p in self.uses_astronomy() else ' inactive') for p in astronomy)
        return text+('; '+', '.join(layers) if layers else '')

    def resource_paths(self):
        paths=self._resource_paths()
        if self.uses_lunar_camera() and Path(PLANET_MAPS['moon']) not in paths:paths.append(Path(PLANET_MAPS['moon']))
        return paths

    def _resource_paths(self):
        if self.uses_system():return [Path(PLANET_MAPS[body]) for body in (self.target,*SYSTEMS[self.target])]
        if self.target in PLANET_MAPS:return [Path(PLANET_MAPS[self.target])]
        paths = []
        if self.map_family in MAP_FAMILIES[1:] and self.month in MONTHS:
            paths.append(Path('maps') / self.map_family / f'{self.map_family}.2004{self.month}.3x5400x2700.png')
        if self.night == 'lights2002':
            paths.append(Path('maps/lights/Earthlights_2002.png'))
        for field,filename in LAYER_ASSETS.items():
            if (self.clouds=='snapshot2011' if field=='clouds' else getattr(self,field)!='off'):paths.append(Path(filename))
        return paths

    def appearance_body(self):
        self.validate()
        if (self.map_family, self.night, self.twilight, self.grid) == ('stock', 'stock', 6, 'off'):
            return SAMPLE.read_bytes()
        day = 'earth.jpg' if self.map_family == 'stock' else self.resource_paths()[0].as_posix()
        night = 'night.jpg' if self.night == 'stock' else 'maps/lights/Earthlights_2002.png'
        grid = 'grid=false' if self.grid == 'off' else f'grid=true\ngrid1={90 // int(self.grid)}\ngrid2={self.grid}'
        return (f'# Xplanet configurator Earth appearance v3; no live layers.\n[default]\nshade=30\n\n[earth]\n'
                f'map={day}\nnight_map={night}\ntwilight={int(self.twilight)}\n{grid}\n').encode()

    def body(self,asset_prefix=''):
        body=self._body(asset_prefix)
        return body+LUNAR_BODY if self.uses_lunar_camera() else body

    def _body(self,asset_prefix=''):
        if self.uses_system():
            self.validate()
            grid='grid=false' if self.grid=='off' else f'grid=true\ngrid1={90//int(self.grid)}\ngrid2={self.grid}'
            scales=self.system_scales();uniform=len(set(scales.values()))==1
            effective=number(next(iter(scales.values())))
            header=f'# Xplanet configurator system appearance v11; target={self.target}; scale={effective}'
            if self.uses_orbits():header=f'# Xplanet configurator system appearance v12; target={self.target}; scale={effective}; orbits={self.orbit_color},{int(self.orbit_width)}'
            if not uniform:header=f'# Xplanet configurator system appearance v13; target={self.target}; orbits='+ (f'{self.orbit_color},{int(self.orbit_width)}' if self.uses_orbits() else 'off')
            text=header+'\n[default]\nshade=30\nmax_radius_for_label=0\n\n'
            for body in (self.target,*SYSTEMS[self.target]):
                text+=f'[{body}]\nmap={PLANET_MAPS[body]}\n'
                if body==self.target and self.planet_shade!=30:text+=f'shade={int(self.planet_shade)}\n'
                text+=(grid if body==self.target else 'grid=false')+'\n'
                if body!=self.target:
                    text+=f'magnify={number(scales[body])}\n'
                    if self.uses_orbits():text+=f'draw_orbit=true\norbit={{-0.5,0.5,5}}\norbit_color={self.orbit_color}\narc_thickness={int(self.orbit_width)}\n'
                text+='\n'
            return (text.rstrip('\n')+'\n').encode()
        if self.target in PLANET_MAPS:
            self.validate()
            grid='grid=false' if self.grid=='off' else f'grid=true\ngrid1={90//int(self.grid)}\ngrid2={self.grid}'
            body_labels='max_radius_for_label=0\n' if self.target not in ('moon','mars') else ''
            return (f'# Xplanet configurator planetary appearance v8; no Earth layers.\n[default]\nshade=30\n{body_labels}\n[{self.target}]\n'
                    f'map={PLANET_MAPS[self.target]}\n'+(f'shade={int(self.planet_shade)}\n' if self.planet_shade!=30 else '')+f'{grid}\n').encode()
        body=self.appearance_body()
        if self.places=='on':
            body+=f'marker_file={PLACE_FILE}\nmarker_color={self.place_color}\nmarker_fontsize={int(self.place_size)}\n'.encode()
        if self.routes=='on':
            body+=f'arc_file={ROUTE_FILE}\narc_color={self.route_color}\narc_thickness={int(self.route_width)}\n'.encode()
        if self.relief=='gebco':
            body+=f'bump_map={LAYER_ASSETS["relief"]}\nbump_scale={number(self.relief_scale)}\n'.encode()
            if self.relief_shadow=='shade':body+=f'bump_shade={int(self.relief_shade)}\n'.encode()
        if self.specular=='bundled':body+=f'specular_map={LAYER_ASSETS["specular"]}\n'.encode()
        if self.clouds=='snapshot2011' or self.uses_capture():
            cloud=IMAGE_FILE if self.uses_capture() else LAYER_ASSETS['clouds']
            body+=f'cloud_map={cloud}\ncloud_gamma={number(self.cloud_gamma)}\ncloud_threshold={int(self.cloud_threshold)}\n'.encode()
        for product in self.uses_observations():
            marker,arc,_=observation_names(product)
            body+=f'marker_file={marker}\n'.encode()
            if product=='storm':body+=f'arc_file={arc}\n'.encode()
        for product in self.uses_astronomy():
            first,second=ASTRONOMY_FILES[product]
            body+=(f'satellite_file={first}\n' if product=='norad' else f'marker_file={first}\narc_file={second}\n').encode()
        return body_names(body,asset_prefix)

    def eclipse_bounds(self):
        parts=self.eclipse_window.split('/')
        if len(parts)!=2:raise ValueError('Invalid eclipse interval.')
        start,end=map(utc_date,parts)
        if not start<end or (end-start).total_seconds()>86400:raise ValueError('Invalid eclipse interval.')
        return start,end

    def uses_astronomy(self):
        if self.target!='earth':return ()
        active=[]
        if self.norad_layer=='captured' and self.time_mode=='now':active.append('norad')
        if self.eclipse_layer=='captured' and self.time_mode=='fixed':
            try:
                start,end=self.eclipse_bounds()
                if start<=utc_date(self.utc)<=end:active.append('eclipse')
            except (ValueError,TypeError):pass
        return tuple(active)

    def astronomy_problem(self,astronomy):
        astronomy=astronomy or {}
        if not isinstance(astronomy,dict) or not set(astronomy)<=set(ASTRONOMY_FILES):return 'Unexpected frozen astronomy association.'
        for product in ASTRONOMY_FILES:
            identity=getattr(self,product+'_id');frozen=astronomy.get(product)
            if identity:
                if not isinstance(frozen,FrozenAstronomy) or frozen.product!=product or frozen.identity!=identity:return 'Retained '+product+' capture is missing or mismatched; reopen or capture explicitly.'
            elif frozen is not None:return 'Unexpected '+product+' data does not match this scene.'
            if product=='eclipse' and self.eclipse_window!=(frozen.window_token if frozen else ''):return 'Eclipse interval does not match retained provenance.'
            if self.target=='earth' and getattr(self,product+'_layer')=='captured' and self.time_mode==('now' if product=='norad' else 'fixed') and not identity:return 'Explicitly capture '+product+' before Preview or Save.'
        return None

    def uses_observations(self):
        return tuple(p for p in OBS_PRODUCTS if getattr(self,p+'_layer')=='captured') if self.target=='earth' and self.time_mode=='now' else ()

    def observation_problem(self,observations):
        if self.observations_id:
            if not isinstance(observations,FrozenObservations) or observations.identity!=self.observations_id:
                return 'Retained observations are missing or mismatched; reopen the saved scene or capture explicitly.'
        elif observations is not None:return 'Unexpected observation data does not match the scene.'
        if self.uses_observations() and (observations is None or not set(self.uses_observations())<=set(observations.metadata['products'])):
            return 'Explicitly capture every selected observation product before Preview or Save.'
        return None

    def uses_capture(self):
        return self.target=='earth' and self.clouds=='captured' and self.time_mode=='now'

    def capture_problem(self,capture):
        if self.capture_id:
            if not isinstance(capture,FrozenCloud) or capture.identity!=self.capture_id:
                return 'The retained cloud capture is missing or mismatched; restore the saved scene or capture explicitly.'
        elif capture is not None:
            return 'Unexpected captured cloud data does not match the scene.'
        elif self.uses_capture():
            return 'Capture existing TotalMarker clouds explicitly before Preview or Save.'
        return None

    def auxiliary_files(self, *, active_only=False):
        self.validate()
        files={}
        if self.uses_lunar_camera():files[ORIGIN_FILE]=self.origin_data()
        if active_only and self.target!='earth':return files
        for mode,text,name in ((self.places,self.places_text,PLACE_FILE),(self.routes,self.routes_text,ROUTE_FILE)):
            if mode=='on' or (text and not active_only):files[name]=HEADERS[name]+text.encode('utf-8')
        return files

    def render_digest(self):
        digest=hashlib.sha256(self.body())
        digest.update("\0".join(self.arguments()).encode())
        for name,data in self.auxiliary_files(active_only=True).items():
            digest.update(name.encode());digest.update(data)
        if self.uses_capture():digest.update(self.capture_id.encode())
        if self.uses_observations():digest.update(self.observations_id.encode())
        for product in self.uses_astronomy():digest.update(getattr(self,product+'_id').encode())
        if 'eclipse' in self.uses_astronomy():digest.update(self.eclipse_window.encode())
        return digest.hexdigest()

    def definition(self, renderer, *, version=16, asset_root=ROOT, asset_prefix=''):
        self.validate()
        scene_prefix(asset_prefix)
        mode = 'space' if self.projection == 'space' else 'map'
        projection = '' if mode == 'space' else self.projection
        if version not in SCENE_HEADERS.values():raise ValueError('Unsupported scene version.')
        header = next(header for header,value in SCENE_HEADERS.items() if value==version)
        if version<16 and (self.norad_layer!='off' or self.norad_id or self.eclipse_layer!='off' or self.eclipse_id or self.eclipse_window):raise ValueError('Older formats cannot retain astronomy captures.')
        if version<15 and (self.camera_mode!='centre' or (self.orbit_latitude,self.orbit_longitude,self.orbit_range,self.frame_x,self.frame_y)!=(0,145,2,50,50)):raise ValueError('Older formats cannot retain orbital camera or frame-centre settings.')
        if version<14 and self.geometry!=LEGACY_GEOMETRY:raise ValueError('Older formats require the legacy 800x600 geometry.')
        if version<13 and self.moon_scales:raise ValueError('Older formats cannot retain individual moon overrides.')
        if version<12 and (self.orbit_paths!='off' or self.orbit_color!='cyan' or self.orbit_width!=1):raise ValueError('Older formats cannot retain orbital path settings.')
        if version<11 and (self.composition!='target' or self.satellite_scale!=1):raise ValueError('Older formats cannot retain system composition settings.')
        if version<10 and (self.observations_id or any(getattr(self,p+'_layer')!='off' for p in OBS_PRODUCTS)):
            raise ValueError('Older formats cannot retain observational layers.')
        if version<8 and (self.target!='earth' or self.observer=='earth'):raise ValueError('Older formats cannot retain planetary choices.')
        if version<9 and (self.planet_shade!=30 or self.target not in ('earth','moon','mars') or self.observer not in ('geographic','earth','moon','sun','opposite_sun')):
            raise ValueError('Older formats cannot retain expanded planetary settings.')
        camera_defaults=replace(self,longitude_mode='longitude',solar_hour=12,distance=1000,north='body',rotation=0)
        if version<7 and self!=camera_defaults:raise ValueError('Older formats cannot retain composition settings.')
        if version<6 and (self.capture_id or self.clouds=='captured'):raise ValueError('Older formats cannot retain captured clouds.')
        layer_defaults=replace(self,relief='off',relief_scale=1,relief_shadow='night',relief_shade=30,
                               specular='off',clouds='off',cloud_gamma=1,cloud_threshold=90)
        if version<5 and self!=layer_defaults:raise ValueError('Older formats cannot retain layer settings.')
        geographic_defaults=replace(self,places='off',places_text='',place_color='yellow',place_size=14,
                                    routes='off',routes_text='',route_color='cyan',route_width=2)
        if version<4 and self!=geographic_defaults:raise ValueError('Older formats cannot retain geographic settings.')
        if version == 2 and self != View(self.latitude, self.longitude, self.projection, self.observer, self.framing, self.radius, self.fov, self.time_mode, self.utc,geometry=LEGACY_GEOMETRY):
            raise ValueError('V2 cannot retain appearance settings.')
        extra = (f'XPLANET_ASSET_ROOT={shlex.quote(str(asset_root))}\nXPLANET_MAP_FAMILY={self.map_family}\n'
                 f'XPLANET_MAP_MONTH={self.month}\nXPLANET_NIGHT={self.night}\nXPLANET_TWILIGHT={number(self.twilight)}\n'
                 f'XPLANET_GRID={self.grid}\nXPLANET_LABEL={self.label}\n') if version >= 3 else ''
        if version>=4:
            files=self.auxiliary_files()
            extra+=(f'XPLANET_PLACES={self.places}\nXPLANET_PLACES_FILE={asset_prefix+PLACE_FILE if PLACE_FILE in files else ""}\n'
                    f'XPLANET_PLACE_COLOR={self.place_color}\nXPLANET_PLACE_SIZE={number(self.place_size)}\n'
                    f'XPLANET_ROUTES={self.routes}\nXPLANET_ROUTES_FILE={asset_prefix+ROUTE_FILE if ROUTE_FILE in files else ""}\n'
                    f'XPLANET_ROUTE_COLOR={self.route_color}\nXPLANET_ROUTE_WIDTH={number(self.route_width)}\n')
        if version>=5:
            extra+=(f'XPLANET_RELIEF={self.relief}\nXPLANET_RELIEF_SCALE={number(self.relief_scale)}\n'
                    f'XPLANET_RELIEF_SHADOW={self.relief_shadow}\nXPLANET_RELIEF_SHADE={number(self.relief_shade)}\n'
                    f'XPLANET_SPECULAR={self.specular}\nXPLANET_CLOUDS={self.clouds}\n'
                    f'XPLANET_CLOUD_GAMMA={number(self.cloud_gamma)}\nXPLANET_CLOUD_THRESHOLD={number(self.cloud_threshold)}\n')
        if version>=6:extra+=f'XPLANET_CLOUD_CAPTURE={self.capture_id}\n'
        if version>=7:
            extra+=(f'XPLANET_LONGITUDE_MODE={self.longitude_mode}\nXPLANET_SOLAR_HOUR={number(self.solar_hour)}\n'
                    f'XPLANET_DISTANCE={number(self.distance)}\nXPLANET_NORTH={self.north}\nXPLANET_ROTATION={number(self.rotation)}\n')
        if version>=8:extra+=f'XPLANET_TARGET={self.target}\n'
        if version>=9:extra+=f'XPLANET_PLANET_SHADE={number(self.planet_shade)}\n'
        if version>=10:
            extra+=''.join(f'XPLANET_{p.upper()}_LAYER={getattr(self,p+"_layer")}\n' for p in OBS_PRODUCTS)
            extra+=f'XPLANET_OBSERVATIONS={self.observations_id}\n'
        if version>=11:extra+=f'XPLANET_COMPOSITION={self.composition}\nXPLANET_SATELLITE_SCALE={number(self.satellite_scale)}\n'
        if version>=12:extra+=f'XPLANET_ORBIT_PATHS={self.orbit_paths}\nXPLANET_ORBIT_COLOR={self.orbit_color}\nXPLANET_ORBIT_WIDTH={number(self.orbit_width)}\n'
        if version>=13:extra+=f'XPLANET_MOON_SCALES={shlex.quote(self.moon_scales)}\n'
        if version>=15:extra+=(f'XPLANET_CAMERA_MODE={self.camera_mode}\nXPLANET_ORBIT_LATITUDE={number(self.orbit_latitude)}\nXPLANET_ORBIT_LONGITUDE={number(self.orbit_longitude)}\nXPLANET_ORBIT_RANGE={number(self.orbit_range)}\nXPLANET_FRAME_X={number(self.frame_x)}\nXPLANET_FRAME_Y={number(self.frame_y)}\nXPLANET_ORIGIN_FILE={asset_prefix+ORIGIN_FILE if self.uses_lunar_camera() else ""}\n')
        if version>=16:extra+=(f'XPLANET_NORAD_LAYER={self.norad_layer}\nXPLANET_NORAD_CAPTURE={self.norad_id}\nXPLANET_ECLIPSE_LAYER={self.eclipse_layer}\nXPLANET_ECLIPSE_CAPTURE={self.eclipse_id}\nXPLANET_ECLIPSE_WINDOW={self.eclipse_window}\n')
        return (f'{header}\nXPLANET_BIN={shlex.quote(str(renderer))}\n'
                'XPLANET_HOME="$project_root"\nXPLANET_CONFIG="$project_root/config"\n'
                f'XPLANET_SCENE_MODE={mode}\nXPLANET_PROJECTION={projection}\n'
                f'XPLANET_OBSERVER={self.observer}\nXPLANET_GEOMETRY={self.geometry}\n'
                f'XPLANET_LATITUDE={number(self.latitude)}\nXPLANET_LONGITUDE={number(self.longitude)}\n'
                f'XPLANET_FRAMING={self.framing}\nXPLANET_RADIUS={number(self.radius)}\nXPLANET_FOV={number(self.fov)}\n'
                f'XPLANET_TIME_MODE={self.time_mode}\nXPLANET_UTC={self.utc}\nEARTH_MAP_PRE=stock\n' + extra)

    def legacy_definition(self, renderer):
        """Recognition only: preserve the foundation format as an explicit case."""
        self.validate()
        if self.projection not in MAP_PROJECTIONS or self != View(self.latitude, self.longitude, self.projection,geometry=LEGACY_GEOMETRY):
            raise ValueError('The original format cannot retain the new camera/time settings.')
        return (f'{LEGACY_HEADER}\nXPLANET_BIN={shlex.quote(str(renderer))}\n'
                'XPLANET_HOME="$project_root"\nXPLANET_CONFIG="$project_root/config"\n'
                f'XPLANET_PROJECTION={self.projection}\nXPLANET_GEOMETRY=800x600\n'
                f'XPLANET_LATITUDE={self.latitude:g}\nXPLANET_LONGITUDE={self.longitude:g}\n'
                'EARTH_MAP_PRE=stock\n')


@dataclass(frozen=True)
class ViewDocument:
    view: View
    saved_renderer: str
    config: bytes
    source: Path | None = None
    capture: FrozenCloud | None = None
    named_source: bool = False
    observations: FrozenObservations | None = None
    native_files: tuple = field(default=(),repr=False)
    astronomy: tuple = field(default=(),repr=False)



_PREVIOUS_MAP_FOLDERS = {
    '0sun': '00-00-sun',
    '1mercury': '01-00-mercury',
    '2venus': '02-00-venus',
    '3moon': '03-01-moon',
    '40mars': '04-00-mars',
    '41phobos': '04-01-phobos',
    '42deimos': '04-02-deimos',
    '50jupiter': '05-00-jupiter',
    '51io': '05-01-io',
    '52europa': '05-02-europa',
    '53ganymede': '05-03-ganymede',
    '54callisto': '05-04-callisto',
    '60saturn': '06-00-saturn',
    '61mimas': '06-01-mimas',
    '62enceladus': '06-02-enceladus',
    '63tethys': '06-03-tethys',
    '64dione': '06-04-dione',
    '65rhea': '06-05-rhea',
    '66titan': '06-06-titan',
    '67hyperion': '06-07-hyperion',
    '68iapetus': '06-08-iapetus',
    '69phoebe': '06-09-phoebe',
    '70uranus': '07-00-uranus',
    '71miranda': '07-01-miranda',
    '72ariel': '07-02-ariel',
    '73umbriel': '07-03-umbriel',
    '74titania': '07-04-titania',
    '75oberon': '07-05-oberon',
    '80neptune': '08-00-neptune',
    '81triton': '08-01-triton',
    '82nereid': '08-02-nereid',
    '90pluto': '09-00-pluto',
    '91charon': '09-01-charon',
}

def current_map_body(config):
    """Normalize only known map path spellings for exact-body recognition."""
    result=config.replace(b'=assets/maps/', b'=maps/')
    for previous,current in _PREVIOUS_MAP_FOLDERS.items():
        result=result.replace(('/solarsystem/'+previous+'/').encode(),('/solarsystem/'+current+'/').encode())
    return result


def parse_saved_view(definition: bytes, config: bytes, *, places=None, routes=None, capture=None, observations=None, origin=None, asset_prefix='', astronomy=()):
    """Recognize versioned exact native output formats, not arbitrary shell syntax."""
    try:
        if not isinstance(astronomy,tuple) or any(not isinstance(item,FrozenAstronomy) for item in astronomy):raise ValueError('Invalid astronomy association.')
        scene_prefix(asset_prefix)
        text = definition.decode('utf-8')
        lines = text.split('\n')
        values = dict(line.split('=', 1) for line in lines[1:-1])
        tokens = shlex.split(values['XPLANET_BIN'])
        if len(tokens) != 1:
            raise ValueError
        renderer = tokens[0]
        if not Path(renderer).is_absolute() or any(c in renderer for c in '\r\n\0'):
            raise ValueError
        projection = values['XPLANET_PROJECTION']
        version=SCENE_HEADERS.get(lines[0],0)
        if version>=2:
            if values['XPLANET_SCENE_MODE'] == 'space':
                projection = 'space'
            view = View(float(values['XPLANET_LATITUDE']), float(values['XPLANET_LONGITUDE']), projection,
                        values['XPLANET_OBSERVER'], values['XPLANET_FRAMING'],
                        float(values['XPLANET_RADIUS']), float(values['XPLANET_FOV']),
                        values['XPLANET_TIME_MODE'], values['XPLANET_UTC'],geometry=values['XPLANET_GEOMETRY'] if version>=14 else LEGACY_GEOMETRY,target=values['XPLANET_TARGET'] if version>=8 else 'earth')
            if version>=3:
                view = replace(view, map_family=values['XPLANET_MAP_FAMILY'], month=values['XPLANET_MAP_MONTH'],
                               night=values['XPLANET_NIGHT'], twilight=float(values['XPLANET_TWILIGHT']),
                               grid=values['XPLANET_GRID'], label=values['XPLANET_LABEL'])
                roots = shlex.split(values['XPLANET_ASSET_ROOT'])
                if len(roots) != 1 or not Path(roots[0]).is_absolute() or any(c in roots[0] for c in '\r\n\0'):
                    raise ValueError
                if version>=4:
                    view=replace(view,places=values['XPLANET_PLACES'],places_text=read_rows(places,PLACE_FILE),
                                 place_color=values['XPLANET_PLACE_COLOR'],place_size=float(values['XPLANET_PLACE_SIZE']),
                                 routes=values['XPLANET_ROUTES'],routes_text=read_rows(routes,ROUTE_FILE),
                                 route_color=values['XPLANET_ROUTE_COLOR'],route_width=float(values['XPLANET_ROUTE_WIDTH']))
                    if view.auxiliary_files()!={name:data for name,data in ((PLACE_FILE,places),(ROUTE_FILE,routes)) if data is not None}:
                        raise ValueError
                if version>=5:
                    view=replace(view,relief=values['XPLANET_RELIEF'],relief_scale=float(values['XPLANET_RELIEF_SCALE']),
                                 relief_shadow=values['XPLANET_RELIEF_SHADOW'],relief_shade=float(values['XPLANET_RELIEF_SHADE']),
                                 specular=values['XPLANET_SPECULAR'],clouds=values['XPLANET_CLOUDS'],
                                 cloud_gamma=float(values['XPLANET_CLOUD_GAMMA']),cloud_threshold=float(values['XPLANET_CLOUD_THRESHOLD']))
                if version>=6:view=replace(view,capture_id=values['XPLANET_CLOUD_CAPTURE'])
                if version>=7:
                    view=replace(view,longitude_mode=values['XPLANET_LONGITUDE_MODE'],solar_hour=float(values['XPLANET_SOLAR_HOUR']),
                                 distance=float(values['XPLANET_DISTANCE']),north=values['XPLANET_NORTH'],rotation=float(values['XPLANET_ROTATION']))
                if version>=8:view=replace(view,target=values['XPLANET_TARGET'])
                if version>=9:view=replace(view,planet_shade=float(values['XPLANET_PLANET_SHADE']))
                if version>=10:
                    view=replace(view,**{p+'_layer':values['XPLANET_'+p.upper()+'_LAYER'] for p in OBS_PRODUCTS},observations_id=values['XPLANET_OBSERVATIONS'])
                if version>=11:view=replace(view,composition=values['XPLANET_COMPOSITION'],satellite_scale=float(values['XPLANET_SATELLITE_SCALE']))
                if version>=12:view=replace(view,orbit_paths=values['XPLANET_ORBIT_PATHS'],orbit_color=values['XPLANET_ORBIT_COLOR'],orbit_width=float(values['XPLANET_ORBIT_WIDTH']))
                if version>=13:
                    scales=shlex.split(values['XPLANET_MOON_SCALES'])
                    if len(scales)!=1:raise ValueError('Invalid moon scale metadata.')
                    view=replace(view,moon_scales=scales[0])
                if version>=15:view=replace(view,camera_mode=values['XPLANET_CAMERA_MODE'],orbit_latitude=float(values['XPLANET_ORBIT_LATITUDE']),orbit_longitude=float(values['XPLANET_ORBIT_LONGITUDE']),orbit_range=float(values['XPLANET_ORBIT_RANGE']),frame_x=float(values['XPLANET_FRAME_X']),frame_y=float(values['XPLANET_FRAME_Y']))
                if version>=16:view=replace(view,norad_layer=values['XPLANET_NORAD_LAYER'],norad_id=values['XPLANET_NORAD_CAPTURE'],eclipse_layer=values['XPLANET_ECLIPSE_LAYER'],eclipse_id=values['XPLANET_ECLIPSE_CAPTURE'],eclipse_window=values['XPLANET_ECLIPSE_WINDOW'])
                expected = view.definition(renderer,version=version,asset_root=roots[0],asset_prefix=asset_prefix)
            else:
                expected = view.definition(renderer, version=2)
        elif lines[0] == LEGACY_HEADER:
            view = View(float(values['XPLANET_LATITUDE']), float(values['XPLANET_LONGITUDE']), projection,geometry=LEGACY_GEOMETRY)
            expected = view.legacy_definition(renderer)
        else:
            raise ValueError
        # Duplicates, unknowns, ordering, quoting and expansions must reproduce
        # exactly. Dictionary extraction does not make this a general importer.
        if len({item.product for item in astronomy})!=len(astronomy) or view.astronomy_problem({item.product:item for item in astronomy}):raise ValueError
        if view.capture_problem(capture) or view.observation_problem(observations):raise ValueError
        if origin!=view.origin_data():raise ValueError
        expected_config = view.body(asset_prefix) if version>=3 else SAMPLE.read_bytes()
        if text != expected or current_map_body(config) != expected_config:
            raise ValueError
        return ViewDocument(view, renderer, config, capture=capture,observations=observations,astronomy=tuple(astronomy))
    except (ValueError, KeyError, IndexError, UnicodeError) as exc:
        raise ValueError('Unsupported saved view. Open only a recognized configurator-produced '
                         'xp.def/xp.conf pair; arbitrary or edited shell/config files are not imported.') from exc


def recognized_body(config):
    """Accept only exact sample/generated scene bodies; never general config."""
    normalized=current_map_body(config)
    if normalized!=config:
        return recognized_body(normalized)
    if config.endswith(LUNAR_BODY):
        base=config[:-len(LUNAR_BODY)]
        return LUNAR_BODY not in base and b'[moon]' not in base and recognized_body(base)
    if config == SAMPLE.read_bytes():
        return True
    try:
        text = config.decode('utf-8')
        individual=re.fullmatch(r'# Xplanet configurator system appearance v13; target=([a-z]+); orbits=(off|[a-z]+,[0-9]+)',text.partition('\n')[0])
        if individual:
            target=individual[1]
            if target not in SYSTEMS:return False
            scales={};section=None
            for line in text.splitlines()[1:]:
                header=re.fullmatch(r'\[([a-z]+)\]',line)
                if header:section=header[1]
                elif line.startswith('magnify='):
                    if section not in SYSTEMS[target] or section in scales:return False
                    scales[section]=moon_scale_number(line.partition('=')[2])
            if set(scales)!=set(SYSTEMS[target]):return False
            values=dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
            paths=individual[2].split(',')
            view=View(target=target,projection='space',composition='system',moon_scales=encode_moon_scales(scales),
                      planet_shade=float(values.get('shade',30)),grid='off' if 'grid=true' not in text else values.get('grid2'),
                      orbit_paths='off' if paths==['off'] else 'on',orbit_color=paths[0] if len(paths)==2 else 'cyan',orbit_width=float(paths[1]) if len(paths)==2 else 1)
            return config==view.body()
        system=re.fullmatch(r'# Xplanet configurator system appearance v11; target=([a-z]+); scale=([0-9.]+)',text.partition('\n')[0])
        orbits=re.fullmatch(r'# Xplanet configurator system appearance v12; target=([a-z]+); scale=([0-9.]+); orbits=([a-z]+),([0-9]+)',text.partition('\n')[0])
        if system or orbits:
            system=system or orbits
            values=dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
            grid='off' if 'grid=true' not in text else values.get('grid2')
            return config==View(target=system[1],projection='space',composition='system',satellite_scale=float(system[2]),planet_shade=float(values.get('shade',30)),grid=grid,orbit_paths='on' if orbits else 'off',orbit_color=orbits[3] if orbits else 'cyan',orbit_width=float(orbits[4]) if orbits else 1).body()
        prefixes=[]
        for key,name in LOCAL_REFERENCES:
            for value in re.findall(r'^'+key+r'=(.+)$',text,re.M):
                if value.endswith(name):prefixes.append(scene_prefix(value[:-len(name)]))
        if prefixes and len(set(prefixes))!=1:return False
        if prefixes and prefixes[0]:
            for key,name in LOCAL_REFERENCES:
                text=text.replace(f'{key}={prefixes[0]}{name}\n',f'{key}={name}\n')
            config=text.encode()
        astronomy_refs=[]
        for product in ASTRONOMY_FILES:
            first,second=ASTRONOMY_FILES[product]
            refs=[f'satellite_file={first}\n'] if product=='norad' else [f'marker_file={first}\n',f'arc_file={second}\n']
            counts=[text.count(line) for line in refs]
            if any(counts):
                if any(count!=1 for count in counts):return False
                astronomy_refs.extend(refs)
        if astronomy_refs:
            for line in astronomy_refs:text=text.replace(line,'')
            return recognized_body(text.encode())
        observed={}
        for product in OBS_PRODUCTS:
            marker,arc,_=observation_names(product)
            has_marker=f'marker_file={marker}\n' in text;has_arc=f'arc_file={arc}\n' in text
            if has_arc and (product!='storm' or not has_marker):return False
            if product=='storm' and has_marker!=has_arc:return False
            if has_marker:
                observed[product+'_layer']='captured'
                text=text.replace(f'marker_file={marker}\n','')
                if has_arc:text=text.replace(f'arc_file={arc}\n','')
        values = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        for target,path in PLANET_MAPS.items():
            if values.get('map')==path:
                grid='off' if values.get('grid')=='false' else values.get('grid2')
                return config==View(target=target,grid=grid,planet_shade=float(values.get('shade',30))).body()
        family, month = 'stock', '01'
        if values['map'] != 'earth.jpg':
            match = re.fullmatch(r'maps/(world(?:\.topo(?:\.bathy)?)?)/\1\.2004(0[1-9]|1[0-2])\.3x5400x2700\.png', values['map'])
            if not match:
                return False
            family, month = match.groups()
        night = {'night.jpg':'stock', 'maps/lights/Earthlights_2002.png':'lights2002'}[values['night_map']]
        grid = 'off' if values.get('grid','false') == 'false' else values['grid2']
        view = View(map_family=family, month=month, night=night, twilight=float(values.get('twilight',6)), grid=grid)
        if 'marker_file' in values:
            if values['marker_file']!=PLACE_FILE:return False
            view=replace(view,places='on',place_color=values['marker_color'],place_size=float(values['marker_fontsize']))
        if 'arc_file' in values:
            if values['arc_file']!=ROUTE_FILE:return False
            view=replace(view,routes='on',route_color=values['arc_color'],route_width=float(values['arc_thickness']))
        if 'bump_map' in values:
            if values['bump_map']!=LAYER_ASSETS['relief']:return False
            view=replace(view,relief='gebco',relief_scale=float(values['bump_scale']),
                         relief_shadow='shade' if 'bump_shade' in values else 'night',relief_shade=float(values.get('bump_shade',30)))
        if 'specular_map' in values:
            if values['specular_map']!=LAYER_ASSETS['specular']:return False
            view=replace(view,specular='bundled')
        if 'cloud_map' in values:
            if values['cloud_map'] not in (LAYER_ASSETS['clouds'],IMAGE_FILE):return False
            view=replace(view,clouds='captured' if values['cloud_map']==IMAGE_FILE else 'snapshot2011',cloud_gamma=float(values['cloud_gamma']),cloud_threshold=float(values['cloud_threshold']))
        return config == replace(view,**observed).body()
    except (ValueError, KeyError, UnicodeError):
        return False

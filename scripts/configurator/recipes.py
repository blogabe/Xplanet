"""Offline, explanatory upstream recipes. Never executable presets or downloads."""
from dataclasses import dataclass

GALLERY = 'https://xplanet.sourceforge.net/Gallery/'

@dataclass(frozen=True)
class Recipe:
    page: str
    title: str
    intent: str
    camera: str
    appearance: str
    prerequisites: str
    support: str
    stock: str | None = None

    @property
    def url(self):
        return GALLERY + self.page + '.html'

    def describe(self):
        return '\n\n'.join((self.title, 'Visual intent: '+self.intent,
            'View / command-line scope: '+self.camera,
            'Body configuration scope: '+self.appearance,
            'Files / build / time prerequisites: '+self.prerequisites,
            'Studio coverage: '+self.support,
            ('Related stock starting point: '+self.stock+' (not a reproduction of the upstream image).'
             if self.stock else 'Reference only: no matching stock starting point is offered.'),
            'Official recipe: '+self.url,
            'Historical reference, not a runnable preset. No command, data fetch, renderer, browser or desktop action occurs here.'))

EVENT = ('Studio Fixed UTC and body-origin/framing controls exist; upstream time scales require review. The event and its resource/date coverage '
         'have not been reproduced by this catalogue; a successful preview is not event-accuracy evidence.')
MISSION = ('Reference only for the spacecraft recipe. General origin trajectories, SPICE/kernel imports '
           'and scattering preparation are not supplied by this browser.')
TIME = 'Review the recipe time scale (including any -tt flag), convert deliberately to studio Fixed UTC, and verify backend/ephemeris coverage before a reconstruction.'
RECIPES = (
    Recipe('earth','Earth with Hubble','Show satellite context above a textured Earth.',
        'Random viewpoint, range and radius; bright-star markers.',
        'Earth specular map and satellite styling.',
        'Specular texture, marker data, icon and dated Hubble TLE/satellite files. Historical TLEs are not current data.',
        'Earth appearance, installed sky annotations and bounded Now-only NORAD capture exist; this does not import the historical Hubble recipe.', 'earth-september'),
    Recipe('16820627_venus','Venus occults Jupiter (1682)','Align two planets from a Mercury viewpoint.',
        'Mercury observer, Venus target, historical date, terrestrial-time flag and close framing.', 'Per-body appearance and labels.',
        TIME+' The published recipe uses the external lnx1600.405 ephemeris.', EVENT),
    Recipe('18891102_iapetus','Iapetus in Saturn’s ring shadow (1889)','Explore illumination within a planetary system.',
        'Iapetus observer looking toward the Sun at the historical date.', 'Saturn ring/shadow appearance along the line of sight.',
        TIME+' Ring geometry matters.', EVENT+' The studio does not offer the Sun as a target.', 'saturn-from-iapetus'),
    Recipe('19140503_sun','Jupiter transits the Sun (1914)','Frame a small foreground body against the Sun.',
        'Uranus observer, Sun target, event date and narrow framing.', 'Body scale, colors and labels.', TIME+' Published command uses external unxp1900.405 ephemeris.',
        EVENT+' The studio does not offer the Sun as a target.'),
    Recipe('19950526_saturn','Eclipse of Titan (1995)','See an eclipse in the Saturn system.',
        'Earth observer, Saturn target and dated event geometry.', 'Saturn/Titan appearance and shadow brightness.',TIME,EVENT,'saturn-from-titan'),
    Recipe('19951228_saturn','Triple shadow on Saturn (1995)','See several satellite shadows on one planet.',
        'Event date, viewpoint and framing.', 'Planetary textures and shadow appearance.',TIME,EVENT,'saturn-rings'),
    Recipe('19971111_callisto','Callisto, Io and Jupiter (1997)','Explore a moon-centred system composition.',
        'Callisto observer, Io target, date and framing.', 'Moon and planet textures and shadows.',TIME,EVENT,'jupiter-from-io'),
    Recipe('20021204_eclipse','Four eclipse viewpoints (2002)','Compare the same eclipse from different observers.',
        'Sun, Venus, Johannesburg and centreline viewpoints; origin files carry position/time.',
        'Earth surface and shadow appearance.',TIME+' Inspect origin-file coordinate units and row/frame counts.',
        EVENT+' Static body/geographic viewpoints differ from centreline trajectory playback; an imported eclipse path is not the physical shadow scene.'),
    Recipe('20030508_earth','Earth seen from Mars (2003)','See Earth and Moon at an interplanetary distance.',
        'Mars-origin Earth view, date and small field of view.', 'Earth/Moon textures and scale.',TIME,
        EVENT,'earth-from-moon'),
    Recipe('20030804_occultation','Earth occults Neptune (2003)','Arrange a near/far-body occultation.',
        'Sun observer looking toward Neptune; event geometry and close framing.', 'Body appearance and label choices.',
        TIME+' Published command uses external lnx1900.405 ephemeris and -tt.',EVENT),
    Recipe('20031109_cassini','Cassini at Saturn (2003)','Recreate spacecraft framing by two observer methods.',
        'Interpolated origin table OR SPICE/NAIF origin; date, light-time, orientation and framing.',
        'Saturn/Titan labels and colors.', 'Origin table or complete compatible SPICE kernels with coverage; historical paths must be replaced.',
        MISSION,'saturn-rings'),
    Recipe('20031120_neptune','Neptune from Triton','Explore a moon-to-planet viewpoint.',
        'Triton-origin Neptune view, date and framing.', 'Neptune appearance.',TIME,
        'Body-origin camera principles apply, but Triton is not a supported studio origin.'),
    Recipe('20031202_earth','Earth and Moon from Neptune','Make a distant relationship visible through exaggeration.',
        'Neptune-origin Earth view and framing.', 'Earth/Moon magnify=20 and lunar orbit drawing.',
        'Body ephemerides and textures; magnification is illustrative, not a changed physical orbit.',
        'Body-origin views exist; system magnification/orbit support is bounded and does not reproduce this Earth/Moon recipe.', 'earth-from-moon'),
    Recipe('20040222_mars','Mars from Earth (2004)','Inspect a planetary disk from an Earth viewpoint.',
        'Earth-origin Mars view and framing; the date appears in the prose, not explicitly in the printed command.', 'Mars texture and lighting.',
        TIME+' Published command uses a SPICE file and configuration; resolve their dependencies rather than treating the printed command as self-contained.',MISSION),
    Recipe('20040701_saturn','Cassini arrival (2004)','Follow a spacecraft encounter sequence.',
        'Origin trajectory OR SPICE; field of view and terrestrial north.', 'Constellation arcs and Saturn appearance.',
        'Trajectory or kernels, exact coverage and constellation data. Native origin playback can override num_times; do not treat it as a bounded one-frame preview.',
        MISSION,'saturn-rings'),
    Recipe('20050228_cassini','Cassini at Saturn (2005)','Compose Saturn from a spacecraft.',
        'Spacecraft observer, event time, framing and orientation.', 'Planetary textures and labels.',
        'Historical observer data/kernels and verified coverage; inspect the linked recipe rather than guessing a current position.',MISSION,'saturn-rings'),
    Recipe('20050418_earth','South America: morning and afternoon','Separate lighting/time changes from relief settings.',
        'Same latitude/longitude/radius; change the UTC time.', 'Surface, bump and specular maps; bump_scale=5 and shade=0 in the example.',
        'Resolve actual surface, relief and specular textures. Scene time does not change imagery acquisition date.',
        'Earth camera/time, relief/specular and shade controls are available. Compare two explicit previews; no automatic time sequence.', 'earth-solar-dawn'),
    Recipe('20050615_jupiter','Jupiter: rendering and observation (2005)','Compare a rendered disk with an observation.',
        'Fixed UTC and Earth viewpoint.', 'Jupiter texture and shadow appearance.',TIME+' The photograph is a comparison, not validation of our local build.',EVENT,'jupiter-cloudtops'),
    Recipe('20050802_earth','MESSENGER Earth (2005)','Compare a spacecraft rendering with a photograph.',
        'NAIF spacecraft origin, SPICE/ephemeris, date, geometry, centre and rotation.',
        'Atmosphere and clouds.', 'Complete spacecraft/planet kernels, compatible ephemeris, cloud texture and prepared scattering tables.',MISSION),
    Recipe('20080624_uranus','Triple shadow on Uranus (2008)','Explore satellite shadows from a selected viewpoint.',
        'Saturn observer, Uranus target, event date with -tt and framing.', 'Planet/moon textures and shadows.',TIME+' Studio Uranus texture limitations still apply.',EVENT,'uranus-from-miranda'),
    Recipe('20120606_earth','Venus transit over Earth’s limb (2012)','Build a dramatic off-centre composition.',
        'Coordinates, range, rotation, date, oversized radius and off-frame centre.',
        'Monthly surface, night, cloud, bump, specular and Rayleigh atmosphere; individual Sun/Venus labels suppressed.',
        'Compatible maps/clouds and prepared scattering tables; event geometry/date coverage.',
        'Several Earth controls exist, but general atmosphere preparation and individual body visibility/label editing are not implemented. Not a ready-to-run transit preset.', 'earth-solar-dawn'),
    Recipe('20460429_jupiter','Jupiter/Saturn conjunction (2046)','Frame an apparent planetary conjunction.',
        'Future fixed date, Neptune observer and framing.', 'Planetary appearance and labels.',
        TIME+' Published command uses external lnx1900.405 ephemeris and -tt.',
        EVENT,'jupiter-cloudtops'),
    Recipe('projections','Map projection comparisons','See how a projection changes the same surface view.',
        'Azimuthal, Mercator and Mollweide; same origin and rotation.', 'Grid settings.',
        'Surface map. Projection is not a multi-body space view; rings are not drawn in projected mode.',
        'The studio currently offers rectangular and orthographic, not all gallery projections. Explore those existing controls without claiming equivalent output.', 'earth-september'),
    Recipe('pango','Multilingual place labels','Render labels in several writing systems.',
        'Earth view and marker placement.', 'UTF-8 markers and font styling.',
        'Pango/font support, suitable glyph coverage and correctly encoded marker text; a font name alone is not readiness.',
        'Bounded static place labels exist; this browser does not add rich Pango markup or certify multilingual font rendering.', 'earth-september'),
)


def matching_recipes(query):
    words=query.casefold().split()
    return tuple(recipe for recipe in RECIPES if all(word in recipe.describe().casefold() for word in words))

"""Plain shared disposable fixtures; no test cases or operational access."""
import hashlib, json, struct, tempfile, zlib

from pathlib import Path

from configurator.model import ROOT

from configurator.observation_capture import capture_existing

from totalmarker.quake_geojson import render_marker as quake_marker

from totalmarker.volcano_cap import render_marker as volcano_marker

from totalmarker.storm_model import render_marker as storm_marker, render_arc

def icon():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\0\0'))+chunk(b'IEND',b'')


class ObservationCaptureFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        for folder in ('config','markers','arcs','images','.state/totalmarker'):(self.root/folder).mkdir(parents=True)
        config=(ROOT/'config/totalmarker.example.toml').read_text()
        self.config=self.root/'config/totalmarker.toml';self.config.write_text(config)
        self.state={'schema':1,'products':{}}
        self.install('quake',quake_marker(b'1 2 "M6 image=observed-quake.png" color=Red symbolsize=12\n',1700000000))
        self.install('volcano',volcano_marker(b'3 4 "Cone" align=Above color=Yellow image=none\n',1700000000))
        self.install('storm',storm_marker(b'5 6 "Cyclone" align=Above color=SkyBlue\n',1700000000),render_arc(b'5 6 7 8 color=Blue\n',1700000000))
        self.save_state()

    def install(self,product,marker,arc=None):
        (self.root/'markers'/product).write_bytes(marker)
        row={'marker_sha256':hashlib.sha256(marker).hexdigest(),'installed_at':1700000000,'checked_at':1700000060,'successful_at':1700000000,'last_outcome':'changed'}
        if arc is not None:
            (self.root/'arcs'/product).write_bytes(arc);row.update(arc_sha256=hashlib.sha256(arc).hexdigest(),source_at=1699999900,source_valid_until_at=1700003600)
        if product=='quake':row.update(feed_generated_at=1699999950,latest_origin_at=1699999900)
        self.state['products'][product]=row

    def save_state(self):(self.root/'.state/totalmarker/state.json').write_text(json.dumps(self.state))

    def capture(self,products=('quake','volcano','storm')):return capture_existing(self.root,products,now=1700000100)

    def inventory(self):return {str(p.relative_to(self.root)):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

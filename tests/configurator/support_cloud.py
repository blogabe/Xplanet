"""Plain shared disposable fixtures; no test cases or operational access."""
from pathlib import Path
import tempfile


class CloudCaptureFixture:
    def setUp(self):
        import hashlib,json
        from configurator.model import ROOT
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        for name in ('config','images','.state/totalmarker'):(self.root/name).mkdir(parents=True)
        config=(ROOT/'config/totalmarker.example.toml').read_text().replace('resolution = 4096','resolution = 2048').replace('auth_mode = "none"','auth_mode = "basic"').replace('username = ""','username = "PrivateUser"').replace('password = ""','password = "PrivatePassword"')
        (self.root/'config/totalmarker.toml').write_text(config)
        self.image=(ROOT/'maps/clouds/clouds_26Aug2011_2048.jpeg').read_bytes()
        self.image_path=self.root/'images/clouds-2048.jpg';self.image_path.write_bytes(self.image)
        self.state_path=self.root/'.state/totalmarker/state.json'
        self.record={'image_sha256':hashlib.sha256(self.image).hexdigest(),'source_image_sha256':hashlib.sha256(self.image).hexdigest(),
                     'checked_at':1700000030,'successful_at':1700000020,'installed_at':1700000000,'last_outcome':'failed',
                     'last_error':{'at':1700000030,'message':'Private error details'}}
        self.save_state()

    def save_state(self):
        import json
        self.state_path.write_text(json.dumps({'schema':1,'products':{'clouds':self.record}}))

    def capture(self):
        from configurator.cloud_capture import capture_existing
        return capture_existing(self.root,now=1700000040)

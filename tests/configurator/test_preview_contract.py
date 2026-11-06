"""A finite renderer fixture records the full invocation and creates a real PNG."""
import asyncio,json,os,struct,sys,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
from configurator.model import View
from configurator.workspace import Workspace

SCRIPT=r'''import json,os,pathlib,struct,sys,zlib
a=sys.argv[1:]
out=pathlib.Path(a[a.index('-output')+1])
w,h=map(int,a[a.index('-geometry')+1].split('x'))
def chunk(kind,raw):return struct.pack('>I',len(raw))+kind+raw+struct.pack('>I',zlib.crc32(kind+raw)&0xffffffff)
image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\0\x40\x80'*w)*h))+chunk(b'IEND',b'')
out.write_bytes(image)
(out.parent/'invocation.json').write_text(json.dumps({'args':a,'numeric':os.environ.get('LC_NUMERIC'),'all':os.environ.get('LC_ALL'),'ctype':os.environ.get('LC_CTYPE')}))
'''

class PreviewContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_argv_locale_and_structurally_valid_png(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'finite renderer';binary.write_text('#!'+sys.executable+'\n'+SCRIPT);binary.chmod(0o700)
            workspace=Workspace()
            try:
                with patch.dict(os.environ,{'LC_ALL':'en_US.UTF-8','LC_NUMERIC':'de_DE.UTF-8','PYTHONCOERCECLOCALE':'0'}):
                    image=await workspace.preview(View(geometry='640x360',time_mode='fixed',utc='2000-01-01T12:00:00Z'),str(binary))
                    self.assertEqual(os.environ['LC_NUMERIC'],'de_DE.UTF-8')
                record=json.loads((image.parent/'invocation.json').read_bytes())
                root=Path(__file__).resolve().parents[2]
                self.assertEqual(record['args'],['-body','earth','-projection','rectangular','-latitude','0','-longitude','0','-date','20000101.120000','-geometry','640x360','-searchdir',str(root),'-config',str(image.parent/'xp.conf'),'-searchdir',str(image.parent),'-output',str(image),'-num_times','1','-tmpdir',str(image.parent)])
                self.assertEqual((record['numeric'],record['all'],record['ctype']),('C',None,'en_US.UTF-8'))
                raw=image.read_bytes();position=8;chunks=[]
                self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
                while position<len(raw):
                    length=struct.unpack('>I',raw[position:position+4])[0];kind=raw[position+4:position+8];data=raw[position+8:position+8+length]
                    self.assertEqual(struct.unpack('>I',raw[position+8+length:position+12+length])[0],zlib.crc32(kind+data)&0xffffffff)
                    chunks.append((kind,data));position+=length+12
                self.assertEqual([kind for kind,_ in chunks],[b'IHDR',b'IDAT',b'IEND'])
                self.assertEqual(struct.unpack('>II',chunks[0][1][:8]),(640,360))
                self.assertEqual(len(zlib.decompress(chunks[1][1])),(640*3+1)*360)
            finally:await workspace.stop();workspace.close()

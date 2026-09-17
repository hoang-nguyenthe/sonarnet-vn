import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from shapely.geometry import box, mapping
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from pack_land_mask import pack
from land_mask import get_mask, load_mask


class PackedMaskTests(unittest.TestCase):
    def test_binary_geometry_matches_source_exactly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root/'assets/land_mask'
            directory.mkdir(parents=True)
            source = directory/'vietnam.json.gz'
            geometry = {'land': box(0,0,1,1), 'core': box(.1,.1,.9,.9),
                        'coast': box(1,0,1.1,1), 'shoreline': box(0,0,1,1).boundary}
            data = {'version':'test', 'geometry': {k:mapping(v) for k,v in geometry.items()}}
            source.write_bytes(gzip.compress(json.dumps(data).encode()))
            pack(source, directory/'vietnam.runtime.zip')
            metadata, actual = get_mask(root)
            for key in geometry:
                self.assertEqual(actual[key].wkb, geometry[key].wkb)
            self.assertNotIn('geometry', metadata)
            data['version'] = 'updated'
            source.write_bytes(gzip.compress(json.dumps(data).encode()))
            self.assertEqual(get_mask(root)[0]['version'], 'updated')

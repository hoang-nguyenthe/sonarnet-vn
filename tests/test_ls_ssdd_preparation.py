import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_ls_ssdd import labels_from_xml, split_for


class PreparationTests(unittest.TestCase):
    def test_scene_split_never_leaks_adjacent_chips(self):
        for scene in range(1,16):
            self.assertEqual(split_for(f'{scene:02d}_1_1'), split_for(f'{scene:02d}_30_20'))
        self.assertEqual(split_for('08_1_1'),'train')
        self.assertEqual(split_for('09_1_1'),'val')
        self.assertEqual(split_for('11_1_1'),'test')

    def test_background_and_inclusive_box(self):
        head = '<annotation><size><width>800</width><height>800</height></size>'
        self.assertEqual(labels_from_xml(head+'</annotation>'), [])
        obj = '<object><name>ship</name><bndbox><xmin>1</xmin><ymin>1</ymin><xmax>800</xmax><ymax>800</ymax></bndbox></object>'
        self.assertEqual(labels_from_xml(head+obj+'</annotation>'), ['0 0.50000000 0.50000000 1.00000000 1.00000000'])

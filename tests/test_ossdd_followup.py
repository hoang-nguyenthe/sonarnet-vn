"""Unit checks for OSSDD's unusual count-prefixed AABB text and duplicate screen."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evaluate_ossdd_followup import difference_hash, duplicate_audit, normalize, parse_aabb


def test_aabb_preserves_source_coordinates_and_accepts_empty_chip():
    assert parse_aabb('0\n') == []
    assert parse_aabb('2\r\n1 0 12.5 512 14\r\n2 0 0 1 1 0.5 0.5\r\n') == [
        [0., 12.5, 512., 14.], [0., 0., 1., 1.]]


@pytest.mark.parametrize('labels', [
    '2\n1 0 0 1 1\n', '1\n1 -1 0 1 1\n', '1\n1 0 0 inf 1\n',
    '1\n1 1 0 0 1\n', '2\n1 1 1 2 2\n1 2 2 3 3\n',
])
def test_aabb_rejects_malformed_source(labels):
    with pytest.raises(ValueError):
        parse_aabb(labels)


def test_normalization_has_defined_flat_case_and_hash():
    assert not normalize(np.zeros((512, 512), dtype=np.float32), 'log1p').any()
    values = np.tile(np.arange(512, dtype=np.float32), (512, 1))
    for mode in ('log1p', 'linear'):
        im = normalize(values, mode)
        assert im.dtype == np.uint8
        assert im.min() == 0 and im.max() == 255
        assert difference_hash(im) == 2**64 - 1


def test_audit_classifies_equal_and_near_cross_set_distinctly():
    a = dict(id='a', split='val', pixels_sha256='x', log8_dhash='0000')
    b = dict(id='b', split='test', pixels_sha256='x', log8_dhash='0000')
    c = dict(id='c', split='test', pixels_sha256='z', log8_dhash='0007')
    assert duplicate_audit([a], [b, c]) == {
        'exact_cross_split': [['a', 'b']], 'exact_within_split': [],
        'perceptual_cross_split': [['a', 'c', 3]], 'perceptual_within_split': [['b', 'c', 3]],
    }

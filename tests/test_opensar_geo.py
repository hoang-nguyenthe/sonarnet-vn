"""Check geospatial metrics on hand-computable fixtures."""
from pathlib import Path
import sys

import numpy as np
import pytest

pytest.importorskip('pyproj')
pytest.importorskip('tifffile')
pytest.importorskip('shapefile')
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_opensar_geo import invalid_runs, pixel_rect, pixel_xy
from evaluate_opensar_geo import assign_unique_support, dimensions, restrict_to_scoring_support


def test_pixel_centers_use_xml_tie_points_and_edges_extend_half_pixel():
    corners = [[0,0], [5110,0], [5110,10220], [0,10220]]
    np.testing.assert_allclose(pixel_xy(corners,[.5,511.5,511.5,.5],[.5,.5,511.5,511.5]), corners)
    assert pixel_rect(corners,0,0,512,512).area == 512**2*200
    np.testing.assert_allclose(dimensions(corners,[0,0,10,15]), [100,300])


def test_missing_pixels_are_exact_not_filled_across_gap():
    valid = np.ones((5,6),dtype=bool)
    valid[1:3,2:4]=False
    valid[3,5]=False
    assert sorted(invalid_runs(valid)) == [(2,1,4,3),(5,3,6,4)]


def test_overlapping_footprint_owns_detections_once():
    corners = [[.5,.5],[511.5,.5],[511.5,511.5],[.5,511.5]]
    rows={i:dict(id=i,scene_id='same',sea=g,labels=[],corners_laea_m=corners) for i,g in (
        ('2',box(5,0,15,10)),('1',box(0,0,10,10)))}
    assign_unique_support(rows)
    assert sum(r['sea'].area for r in rows.values()) == 150
    det = np.array([[6,1,8,3],[12,1,14,3],[20,1,22,3]])
    scores=np.array([.9,.8,.7])
    a, _ = restrict_to_scoring_support(rows['1'],det,scores)
    b, _ = restrict_to_scoring_support(rows['2'],det,scores)
    np.testing.assert_array_equal(a,det[[0]])
    np.testing.assert_array_equal(b,det[[1]])

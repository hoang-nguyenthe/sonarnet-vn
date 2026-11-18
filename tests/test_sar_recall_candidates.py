"""Guard against boundary and model-selection mistakes in SAR follow-ups."""
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('pyproj')
pytest.importorskip('tifffile')
pytest.importorskip('shapefile')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_sar_recall_candidates import ring_statistics, cfar_propose, nms, choose_candidate, patches
from prepare_opensar_confirmation import eligible


def test_guard_and_land_do_not_bias_water_ring():
    values=np.full((15,15),.2); water=np.ones_like(values,dtype=bool)
    values[7,7]=100; values[:,8:]=100; water[:,8:]=False
    mean, sigma, count=ring_statistics(values,water,3,7)
    assert mean[7,7]==pytest.approx(.2)
    assert sigma[7,7]==pytest.approx(.001)
    assert count[7,7]==pytest.approx(22)
    assert mean[0,0]==pytest.approx(.2)


def test_flat_background_no_boxes_and_compact_water_return():
    im=np.full((41,41),40,dtype=np.uint8); water=np.ones_like(im,dtype=bool)
    assert not len(cfar_propose(im,water,7,29,3.)[0])
    im[19:22,19:22]=230
    box,score=cfar_propose(im,water,7,29,3.)
    assert np.array_equal(box,[[16,16,25,25]]) and score[0]>.5


def test_selection_enforces_false_positive_budget_before_recall():
    def record(method, near, tp, fp):
        return dict(method=method, threshold=.10,metrics=dict(matched=near,true_positive=tp,false_positive=fp,f1=.3))
    a=record('reference',10,11,31)
    b=record('contrast',13,13,50)
    c=record('tiles',9,17,32)
    assert choose_candidate([a,b,c],35)==a
    assert choose_candidate([a,b,c],50)==b


def test_patch_coverage_and_nms_order():
    a=np.ones((512,512)); covered=np.zeros_like(a)
    for x,y,im in patches(a):
        covered[y:y+im.shape[0],x:x+im.shape[1]]+=1
    assert covered.min()==1 and covered.max()==4
    b=np.array([[0,0,10,10],[1,1,10,10],[30,30,40,40]])
    out,s=nms(b,np.array([.2,.9,.8]))
    assert np.array_equal(out,b[[1,2]])
    assert np.allclose(s,[.9,.8])


def test_confirmation_excludes_prior_scene_overlap_and_day():
    from shapely.geometry import box, mapping
    def s(split, day, x, reasons=()):
        return dict(split=split,day=day,footprint=mapping(box(x,0,x+.1,.1)),reasons=list(reasons))
    res=eligible(dict(val=s('val','2020-01-01',0),same=s('train','2020-01-01',10),
        near=s('train','2020-01-02',.15), far=s('train','2020-01-03',2),
        train_overlap=s('train','2020-01-03',3,['near_LS_SSDD'])))
    assert [k for k,v in res.items() if v['eligible_for_confirmation']]==['far']

"""Audit the exact OpenSAR boxes and frozen decisions shown for tile 4048."""
import gzip
import json
from pathlib import Path

import numpy as np

from sonarnet.evaluation.detection_metrics import box_iou, evaluate_detections
from sonarnet.evaluation.independent_sar import operational_metrics

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'reports/final'
SAR = BASE/'opensar_adaptation_20261118'
OUT = BASE/'chang2'/'sar-tile-4048.json'
TILE = '4048'
IOU_MINIMUM = .50


def read_gzip(path):
    with gzip.open(path,'rt') as source:
        return json.load(source)


def tile_audit(metrics):
    manifest = read_gzip(BASE/'opensar_confirmation_20261118/confirmation_manifest.json.gz')
    image = next(row for row in manifest['images'] if row['id']==TILE)
    gt = np.asarray([label['box'] for label in image['labels']
                     if label['is_vessel'] and label['evaluated_sea']
                     and label['confidence'] in ('HIGH','MEDIUM')])
    truth = {TILE:gt}
    tile = {'id':TILE,'day':image['day'],'labels':gt.tolist(),
            'iou_minimum':IOU_MINIMUM,'models':{}}
    for name,data in metrics['diagnostic']['models'].items():
        prefix = SAR/('diagnostic_'+name)
        source = read_gzip(prefix.with_name(prefix.name+'_predictions.json.gz'))[TILE]
        expected = next(row for row in read_gzip(prefix.with_name(prefix.name+'_errors.json.gz'))
                        if row['id']==TILE)
        boxes, conf = np.asarray(source['boxes']),np.asarray(source['scores'])
        predictions = {TILE:(boxes,conf)}
        _, audited = operational_metrics([{'id':TILE,'boxes_xyxy':gt,
                                          'scene_id':expected['scene_id']}],predictions,data['threshold'])
        observed = audited[0]
        assert json.loads(json.dumps(observed)) == expected
        overlap = box_iou(boxes,gt)
        predicted = []
        for i,(box,score) in enumerate(zip(boxes,conf)):
            if score<data['threshold']:
                status = 'below_confidence'
            elif i not in expected['false_positive_indices']:
                status = 'matched'
            elif overlap[i].max()>=IOU_MINIMUM:
                status = 'duplicate'
            elif overlap[i].max()>0:
                status = 'below_iou'
            else:
                status = 'no_overlap'
            predicted.append(dict(index=i,box=box.tolist(),confidence=float(score),
                                  overlap_with_label=overlap[i].tolist(),status=status))
        sensitivity = {}
        for threshold in (.30,.50,.75):
            m = evaluate_detections(predictions,truth,iou_threshold=threshold,
                                    score_threshold=data['threshold']).to_dict()
            sensitivity[f'{threshold:.2f}'] = {k:m[k] for k in ('true_positive','false_positive','false_negative')}
        tile['models'][name] = dict(confidence_threshold=data['threshold'],predictions=predicted,
                                    original_counts=expected,iou_sensitivity=sensitivity)
    return tile


def main():
    baseline = json.loads((SAR/'results.json').read_text())['evaluation']
    strategies = {key:json.loads((SAR/key/'results.json').read_text())['evaluation']
                  for key in ('review-budget','coastal-budget')}
    rows = []
    fields = ('true_positive','false_positive','n_ground_truth','precision',
              'recall','benchmark_unmatched_per_km2')
    for cohort,part in baseline.items():
        models = {name:value['metrics'] for name,value in part['models'].items()}
        models.update({key:result[cohort]['metrics'] for key,result in strategies.items()})
        for name,data in models.items():
            rows.append(dict(cohort=cohort,method=name,**{key:data[key] for key in fields}))
    OUT.write_text(json.dumps(dict(tile=tile_audit(baseline),comparison=rows),indent=2)+'\n')
    print(OUT)


if __name__ == '__main__':
    main()

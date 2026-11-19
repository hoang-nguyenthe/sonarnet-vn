"""Learn a radar point heatmap from RTC reference centers and compare review queues."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, maximum_filter
from shapely import intersects_xy
from shapely.geometry import box
import torch
from torch import nn
import torch.nn.functional as F

from evaluate_review_ranking import save
from land_mask import get_mask
from prepare_opensar_geo import unique_water_support
from refresh_detailed_scan import allowed_pixels
from score_vn_reference_rtc import ROOT, digest, geographic_distances, matched, raster_points, valid_water
from sonarnet.data.planetary import gray_rgba

SEED = 20261119
VALIDATION_DAYS = ('20220629', '20220816')
RADII = (50, 100, 150)
MODES = ('equal_incumbent', 'equal_relaxed')
METHODS = ('point_only', 'point_fill_quarter', 'point_fill_half')
PATCH = 96
CANDIDATES_PER_WINDOW = 60
POINT_MINIMUM_SEPARATION_M = 35


class PointDetector(nn.Module):
    def __init__(self):
        super().__init__()
        self.fine = nn.Sequential(nn.Conv2d(2,16,3,padding=1),nn.BatchNorm2d(16),nn.SiLU(),
                                  nn.Conv2d(16,16,3,padding=1),nn.BatchNorm2d(16),nn.SiLU())
        self.context = nn.Sequential(nn.Conv2d(16,24,3,stride=2,padding=1),nn.BatchNorm2d(24),nn.SiLU(),
                                     nn.Conv2d(24,24,3,padding=2,dilation=2),nn.BatchNorm2d(24),nn.SiLU(),
                                     nn.Conv2d(24,24,3,padding=3,dilation=3),nn.BatchNorm2d(24),nn.SiLU())
        self.output = nn.Sequential(nn.Conv2d(40,16,3,padding=1),nn.SiLU(),nn.Conv2d(16,1,1))
        nn.init.constant_(self.output[-1].bias,-2.2)

    def forward(self, inputs):
        fine = self.fine(inputs)
        context = self.context(fine)
        context = F.interpolate(context,size=fine.shape[-2:],mode='bilinear',align_corners=False)
        return self.output(torch.cat((fine,context),dim=1))[:,0]


def prepare_window(gamma, bounds, mask, points):
    rgba = gray_rgba(np.ma.masked_less_equal(gamma,0))
    water, _ = allowed_pixels(Image.fromarray(rgba),bounds,mask)
    grey = np.where(water,rgba[:,:,0]/255.,0).astype(np.float32)
    n = gaussian_filter(water.astype(np.float32),3.)
    average = gaussian_filter(grey,3.) / np.maximum(n,1e-5)
    inputs = np.stack((grey,np.where(water,grey-average,0))).astype(np.float32)
    west,south,east,north = bounds
    h,w = gamma.shape
    lon,lat = np.asarray(points,dtype=float).reshape(-1,2).T
    x = np.floor((lon-west)*w/(east-west)).astype(int)
    y = np.floor((north-lat)*h/(north-south)).astype(int)
    valid = (0 <= x) & (x < w) & (0 <= y) & (y < h)
    x,y = x[valid],y[valid]
    wet = water[y,x]
    xy = np.c_[x[wet],y[wet]]
    target = np.zeros(gamma.shape,dtype=np.float32)
    # A soft disk around the published point allows for pixel quantization.
    # The target covers a location, with no assumed vessel dimensions.
    yy,xx = np.mgrid[-5:6,-5:6]
    kernel = np.exp(-(xx**2+yy**2)/(2*1.45**2)).astype(np.float32)
    padded = np.pad(target,5)
    for px,py in xy:
        window = padded[py:py+11,px:px+11]
        np.maximum(window,kernel,out=window)
    return dict(input=inputs,water=water,targets=padded[5:-5,5:-5],xy=xy,bbox=bounds)


def read_cases(root, cache, selected, mask):
    folder = root/'rtc-512'
    windows = json.loads((folder/'manifest.json').read_text())['cohorts']
    record = {row['scene']:row for row in windows}
    bounds = json.loads((root/'screened.json').read_text())['bounds']
    with gzip.open(cache,'rt') as fd:
        pairs = json.load(fd)
    for case in pairs:
        if not selected(case):
            continue
        cohort = record[case['scene']]
        if cohort['region'] != case['region'] or len(cohort['windows']) != case['windows']:
            raise ValueError('RTC and comparison data differ')
        area = box(*bounds[case['region']])
        chips, areas = [], []
        for row in sorted(cohort['windows'],key=lambda c:c['window_id']):
            path = folder/row['file']
            if digest(path) != row['sha256']:
                raise ValueError('Unexpected RTC raster checksum')
            with np.load(path,allow_pickle=False) as raw:
                gamma = raw['gamma0']
            areas.append(valid_water(gamma,row['bbox'],area,mask[1]['land']))
            chips.append(prepare_window(gamma,row['bbox'],mask,case['truth']))
        for chip,area in zip(chips,unique_water_support(areas)):
            chip['support'] = area
        yield dict(case,chips=chips)


def batch(rng, images, positive, size):
    inputs, targets, masks = [], [], []
    for index in range(size):
        pool = positive if index < size//2 else images
        item = pool[rng.integers(len(pool))]
        h,w = item['water'].shape
        if index < size//2:
            x,y = item['xy'][rng.integers(len(item['xy']))]
            x0 = int(np.clip(x-rng.integers(16,PATCH-16),0,w-PATCH))
            y0 = int(np.clip(y-rng.integers(16,PATCH-16),0,h-PATCH))
        else:
            x0,y0 = rng.integers(w-PATCH+1),rng.integers(h-PATCH+1)
        y,x = slice(y0,y0+PATCH),slice(x0,x0+PATCH)
        flip_x,flip_y = (int(f) for f in rng.choice((-1,1),2))
        inputs.append(item['input'][:,y,x][:,::flip_y,::flip_x])
        targets.append(item['targets'][y,x][::flip_y,::flip_x])
        masks.append(item['water'][y,x][::flip_y,::flip_x])
    return [torch.from_numpy(np.stack(rows)) for rows in (inputs,targets,masks)]


def loss_for(labels, logits, water):
    predicted = logits.sigmoid()
    positive = labels == 1
    negatives = (labels < 1) & water
    ln_positive = F.logsigmoid(logits)
    ln_negative = F.logsigmoid(-logits)
    target_loss = -(ln_positive * (1-predicted).square() * positive).sum()
    background = -(ln_negative * predicted.square() * (1-labels).pow(4) * negatives)
    hard_negatives = torch.topk(background.flatten(), k=1024, sorted=False).values
    return target_loss/(positive.sum()+1) + 4*hard_negatives.mean()


@torch.inference_mode()
def propose(model, case, device):
    model.eval()
    rows, times = [], []
    for chip in case['chips']:
        if chip['support'].is_empty or not chip['water'].any():
            continue
        start = time.perf_counter()
        logits = model(torch.from_numpy(chip['input'][None]).to(device)).detach().cpu().numpy()[0]
        values = np.where(chip['water'],logits,-np.inf)
        maxima = chip['water'] & (values == maximum_filter(values,size=5))
        yy,xx = np.nonzero(maxima)
        order = np.argsort(-values[yy,xx],kind='stable')[:CANDIDATES_PER_WINDOW]
        x,y = xx[order],yy[order]
        lon,lat = raster_points(np.c_[x+.5,y+.5],chip['bbox'],values.shape)
        keep = intersects_xy(chip['support'],lon,lat)
        rows.extend(np.c_[lon[keep],lat[keep],values[y,x][keep]].tolist())
        times.append((time.perf_counter()-start)*1000)
    return sorted(rows,key=lambda p:-p[2]), times


def merge_review(priority, point, backup, limit):
    """Fill a review allotment with spatially distinct detections before backfill."""
    kept = list(priority)
    candidates = point+backup
    if not candidates or len(kept) >= limit:
        return kept[:limit]
    distances_to_kept = geographic_distances(candidates,[p[:2] for p in kept])
    adjacency = geographic_distances(candidates,[p[:2] for p in candidates]) <= POINT_MINIMUM_SEPARATION_M
    selected = []
    for i in range(len(candidates)):
        if len(kept)+len(selected) == limit:
            break
        if not distances_to_kept[i].size or distances_to_kept[i].min() > POINT_MINIMUM_SEPARATION_M:
            if not adjacency[i,selected].any():
                selected.append(i)
    kept.extend(candidates[idx] for idx in selected)
    seen = {tuple(p[:2]) for p in kept}
    for item in backup:
        if len(kept) == limit:
            break
        if tuple(item[:2]) not in seen:
            kept.append(item)
            seen.add(tuple(item[:2]))
    return kept


def score_case(case, point):
    results = {}
    for mode,method in zip(MODES,('incumbent','baseline_low')):
        base = sorted(case[method],key=lambda p:-p[2])
        limit = min(case['budget'],len(base))
        low = sorted(case['baseline_low'],key=lambda p:-p[2])
        queues = {'baseline':base[:limit]}
        for policy,q in zip(METHODS,(0.,.75,.5)):
            queues[policy] = merge_review(base[:int(limit*q)], point, low, limit)
            if len(queues[policy]) != limit:
                raise ValueError('Review allotments differ')
        results[mode] = {key:matched(value,case['truth'],RADII) for key,value in queues.items()}
    full = matched(point,case['truth'],(100,))[100]
    return dict(scene=case['scene'],region=case['region'],windows=case['windows'],candidate_pool=full,**results)


def day(case):
    return case['scene'].split('_')[4][:8]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('development','held-out','confirmation','cached-neural','confirmation-cache','out'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--steps',type=int,default=720)
    args = p.parse_args()
    out = args.out
    out.mkdir(exist_ok=False)
    torch.manual_seed(SEED)
    torch.set_num_threads(4)
    rng = np.random.default_rng(SEED)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    train_cache = args.cached_neural/'development_features.json.gz'
    test_cache = args.cached_neural/'fresh_features.json.gz'
    input_files = {'dev':(args.development,train_cache),'held_out':(args.held_out,test_cache),
                   'confirmation':(args.confirmation,args.confirmation_cache)}
    save(out/'protocol.json',dict(
        started=datetime.now(timezone.utc).isoformat(),code_sha256=digest(Path(__file__)),
        seed=SEED,steps=args.steps,validation_days_utc=VALIDATION_DAYS,device=device,torch=torch.__version__,
        target='1.45 px Gaussian around published point, radar center only',
        patch_px=PATCH,optimizer='AdamW; lr=0.0015; batch=16; focal loss with 1,024 hard negatives',
        max_peaks_per_window=CANDIDATES_PER_WINDOW,review_merge_radius_m=POINT_MINIMUM_SEPARATION_M,
        selection='Every 60 steps, evaluate on two held development days. Select best point challenger by one-to-one matches at exact review counts; prefer earlier checkpoint in a tie.',
        references={name:dict(manifest_sha256=digest(root/'rtc-512/manifest.json'),cache_sha256=digest(cache))
                    for name,(root,cache) in input_files.items()},
        scope='Retrospective historical fixed-review comparisons. Entire acquisition days are separate. Point labels are not physical hull boxes.',
    ))
    mask = get_mask(ROOT)
    development = list(read_cases(args.development,train_cache,lambda c:True,mask))
    validation = [case for case in development if day(case) in VALIDATION_DAYS]
    training = [case for case in development if day(case) not in VALIDATION_DAYS]
    if len(validation) != len(VALIDATION_DAYS):
        raise ValueError('Missing held development day')
    all_chips = [chip for case in training for chip in case['chips'] if chip['water'].any()]
    positive = [chip for chip in all_chips if len(chip['xy'])]
    if not training or not positive:
        raise ValueError('Training has no positive point chips')
    print('Training days', [day(c) for c in training], 'raster windows',len(all_chips),
          'positive windows',len(positive),'training device',device,flush=True)
    model = PointDetector().to(device)
    optimizer = torch.optim.AdamW(model.parameters(),lr=.0015,weight_decay=.002)
    choices, best = [], {mode:None for mode in MODES}
    for step in range(1,args.steps+1):
        model.train()
        xs,targets,water = [value.to(device) for value in batch(rng,all_chips,positive,16)]
        optimizer.zero_grad(set_to_none=True)
        loss = loss_for(targets,model(xs),water)
        if not torch.isfinite(loss):
            raise ValueError('Non-finite model loss')
        loss.backward()
        optimizer.step()
        if step % 60 == 0 or step == args.steps:
            scores = []
            for case in validation:
                points,_ = propose(model,case,device)
                scores.append(score_case(case,points))
            totals = {mode:{method:sum(x[mode][method][100]['matched'] for x in scores)
                            for method in ('baseline',*METHODS)} for mode in MODES}
            checkpoint = out/f'point-step-{step}.pt'
            torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},checkpoint)
            for mode in MODES:
                name = max(METHODS,key=totals[mode].__getitem__)
                matched_count = totals[mode][name]
                if best[mode] is None or matched_count > best[mode]['matched']:
                    best[mode] = dict(method=name,step=step,matched=matched_count,
                                      checkpoint=checkpoint.name,checkpoint_sha256=digest(checkpoint))
            choices.append(dict(step=step,loss=float(loss.detach().cpu()),results=scores))
            print(step,totals,flush=True)
    save(out/'selection.json',dict(locked_at=datetime.now(timezone.utc).isoformat(),selected=best,development=choices))
    used = {day(c) for c in development}
    result = dict(selection_sha256=digest(out/'selection.json'),test={})
    for kind,(root,cache) in input_files.items():
        if kind == 'dev':
            continue
        group = list(read_cases(root,cache,lambda c:True,mask))
        if {day(c) for c in group} & used:
            raise ValueError('Previously used acquisition day in test')
        cases = []
        for case in group:
            reports = {}
            for mode in MODES:
                spec = best[mode]
                model.load_state_dict(torch.load(out/spec['checkpoint'],weights_only=True))
                points,times = propose(model,case,device)
                summary = score_case(case,points)
                reports[mode] = dict(method=spec['method'],counts=summary[mode],
                                     candidate_pool=summary['candidate_pool'],
                                     heatmap_p50_ms=float(np.median(times)) if times else None)
            cases.append(dict(scene=case['scene'],region=case['region'],windows=case['windows'],modes=reports))
            print(kind,day(case),[(m,reports[m]['counts'][reports[m]['method']][100]['matched']) for m in MODES],flush=True)
        result['test'][kind] = cases
        save(out/'results.json',result)


if __name__ == '__main__':
    main()

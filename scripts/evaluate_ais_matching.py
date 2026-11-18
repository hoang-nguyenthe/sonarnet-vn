#!/usr/bin/env python3
"""Deterministic synthetic stress cases for AIS association, not real-world accuracy.

Run: python scripts/evaluate_ais_matching.py --output reports/final/ais_matching
Includes the legacy distance-only Hungarian baseline using identical input.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sonarnet.config import RunConfig
from sonarnet.data.geo import haversine_m
from sonarnet.fusion.kalman import KalmanEstimate
from sonarnet.fusion.matching import Detection, SARAISFusion, solve_assignment


def legacy(dets, estimates):
    keys = list(estimates)
    if not keys:
        return {}
    cost = np.array([[float(haversine_m(d.lat, d.lon, estimates[m].lat, estimates[m].lon)) for m in keys] for d in dets])
    rows, cols = solve_assignment(np.where(cost <= 500., cost, np.inf))
    return {int(i): keys[j] for i, j in zip(rows, cols) if cost[i, j] <= 500.}


def run(out):
    cfg = RunConfig()
    cfg.fusion.preserve_proposed_pair = False
    fusion = SARAISFusion(cfg)
    rng = np.random.default_rng(20261116)
    cases, totals = [], []
    scenarios = ['fresh_separated', 'crossing_ambiguous', 'noisy_ais', 'stale_ais', 'missing_ais', 'unknown_sigma']
    for scenario in scenarios:
        counts = {method: Counter() for method in ['distance_only', 'quality_gated']}
        reasons = Counter()
        for trial in range(100):
            true_x = [0., 600.] if scenario != 'crossing_ambiguous' else [-5., 5.]
            dets = [Detection(i, 0., (x + rng.normal(0, 5))/111195., 80., 20., (0, 0, 8, 2)) for i, x in enumerate(true_x)]
            estimates = {}
            for i, x in enumerate(true_x):
                noise = 350. if scenario == 'noisy_ais' else 10.
                sigma = 350. if scenario == 'noisy_ais' else 20.
                if scenario == 'unknown_sigma':
                    sigma = float('nan')
                if scenario != 'missing_ais':
                    estimates[100 + i] = KalmanEstimate(0., (x + rng.normal(0, noise))/111195., 0., 0., sigma, 600. if scenario == 'stale_ais' else 10., 5)
            safe_matches, distances, why = fusion.match_with_reasons(dets, estimates)
            for method, matched in [('distance_only', legacy(dets, estimates)), ('quality_gated', safe_matches)]:
                counts[method]['detections'] += len(dets)
                counts[method]['accepted'] += len(matched)
                counts[method]['correct_identity'] += sum(m == 100 + i for i, m in matched.items())
                counts[method]['wrong_identity'] += sum(m != 100 + i for i, m in matched.items())
                counts[method]['abstained'] += len(dets) - len(matched)
                counts[method]['unsafe_accepted'] += len(matched) if scenario != 'fresh_separated' else 0
            reasons.update(why)
            cases.append({'scenario': scenario, 'trial': trial, 'matches': safe_matches, 'reasons': why, 'distances_m': distances})
        for method, metrics in counts.items():
            totals.append({'scenario': scenario, 'method': method, **{k: metrics[k] for k in ['detections','accepted','correct_identity','wrong_identity','abstained','unsafe_accepted']}})
    out.mkdir(parents=True, exist_ok=True)
    with (out/'summary.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(totals[0]))
        writer.writeheader()
        writer.writerows(totals)
    (out/'cases.json').write_text(json.dumps({'dataset_type': 'synthetic_stress_test', 'seed': 20261116, 'thresholds': vars(cfg.fusion), 'cases': cases}, indent=2, ensure_ascii=False, allow_nan=False))
    lines = ['# Kiểm tra ghép AIS có cơ chế từ chối', '', 'Dữ liệu mô phỏng có chủ đích, 100 lần mỗi tình huống, 2 ứng viên/lần. Cùng đầu vào cho baseline khoảng cách (500 m) và phương pháp mới. Không dùng kết quả này làm độ chính xác trên AIS thực địa.', '', '| Tình huống | Phương pháp | Ghép đúng danh tính | Ghép sai danh tính | Từ chối | Ghép dù dữ liệu không đủ an toàn |', '|---|---|---:|---:|---:|---:|']
    for row in totals:
        lines.append('| {scenario} | {method} | {correct_identity} | {wrong_identity} | {abstained} | {unsafe_accepted} |'.format(**row))
    lines += ['', 'Đúng danh tính là so với nhãn mô phỏng. Ghép tình cờ đúng nhưng quá cũ/nhiễu/cắt nhau vẫn tính là ghép không đủ an toàn. Từ chối có đánh đổi giảm số ghép, cần chuyên viên kiểm tra.', '', 'Ngưỡng nghiên cứu mặc định: tuổi ≤180 giây, sigma vị trí ≤150 m, khoảng cách ≤min(500 m, 3 × sqrt(sigma_AIS² + 30²)). Từ chối khi hai ứng viên cạnh tranh có chênh khoảng cách ≤max(30 m, sigma kết hợp). Chưa hiệu chỉnh trên AIS thực địa.', '', 'Lệnh tái hiện: `python scripts/evaluate_ais_matching.py --output reports/final/ais_matching`', 'Kiểm thử: `python -m unittest discover -s tests -p test_fusion_quality_gates.py`', '', 'CSV giữ bảng đếm; cases.json giữ 600 ca, lý do và khoảng cách ghép. Độ bất định đầu vào trong stress test được điều khiển rõ ràng. Test riêng trong unittest kiểm tra Kalman tăng sigma khi quỹ đạo nhiễu.']
    (out/'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(totals, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('reports/final/ais_matching'))
    run(parser.parse_args().output)

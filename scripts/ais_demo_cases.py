"""Shared synthetic AIS evidence cases for Streamlit and the public site."""
from itertools import product
import json

from sonarnet.config import RunConfig
from sonarnet.fusion.kalman import KalmanEstimate
from sonarnet.fusion.matching import Detection, SARAISFusion
from sonarnet.fusion.status import MISSING_DATA, STATE_LABELS, pending_review

SCENARIOS = {
    'Thiếu AIS': 'missing',
    'AIS ở ngoài vùng ghép': 'distant',
    'Kích thước mâu thuẫn': 'conflict',
    'Thiếu kích thước khai báo': 'missing_size',
    'AIS quá cũ': 'stale',
    'AIS gần nhất đã cũ, có tín hiệu khác gần đó': 'stale_nearby',
    'Hai quỹ đạo giao nhau': 'crossing',
    'Chuỗi AIS lệch vị trí': 'bias',
    'Dữ liệu đủ điều kiện ghép': 'clean',
}
REASONS = {
    'no_ais': 'Không có AIS để đối chiếu',
    'out_of_range': 'Không có AIS trong ngưỡng ghép',
    'stale_ais': 'AIS cách thời điểm chụp quá xa',
    'uncertain_position': 'Độ bất định vị trí vượt ngưỡng',
    'invalid_ais': 'AIS thiếu hoặc có giá trị không hợp lệ',
    'ambiguous': 'Nhiều ứng viên cạnh tranh; chưa thể chọn',
    'assigned_elsewhere': 'Không có cặp duy nhất trong phép gán',
    'matched': 'Đạt điều kiện ghép vị trí',
    'invalid_detection': 'Tọa độ SAR không hợp lệ',
}


def run_scenario(kind, age_s=None, sigma_m=20.):
    """Illustrative inputs go through the production association/classification code."""
    cfg = RunConfig()
    fusion = SARAISFusion(cfg)
    positions = {'crossing': [-5., 5.], 'bias': [-70., 70.]}.get(kind, [0.])
    detections = [Detection(i, 0., x / 111195., 80., 20., (0, 0, 8, 2))
                  for i, x in enumerate(positions)]
    estimates = {}
    positions_ais = {}
    if kind != 'missing':
        for i, x in enumerate(positions):
            offset = 700. if kind == 'distant' else 3.
            if kind == 'bias':
                offset = (160., -160.)[i]
            age = age_s if age_s is not None else (600. if kind in {'stale','stale_nearby'} else 10.)
            estimate = KalmanEstimate(0., (x + offset) / 111195., 0., 0., sigma_m, age, 5)
            estimate.declared_length_m = float('nan') if kind == 'missing_size' else (200. if kind == 'conflict' else 80.)
            estimates[100 + i] = estimate
            positions_ais[100 + i] = x + offset
    if kind == 'stale_nearby':
        estimates[101] = KalmanEstimate(0.,80/111195.,0.,0.,20.,10.,5)
        positions_ais[101] = 80.
    matches, distances, reasons = fusion.match_with_reasons(detections, estimates)
    states = fusion.classify_states(detections, matches, estimates, reasons)
    rows = []
    for i, state in enumerate(states):
        explanation = REASONS[reasons[i]]
        if i in matches and state == MISSING_DATA:
            explanation += '. Thiếu kích thước để đối chiếu.'
        elif state == 'AIS_MISMATCH':
            explanation += '. Kích thước vượt ngưỡng sai lệch.'
        rows.append({
            'Điểm SAR': f'Điểm {i + 1}',
            'Trạng thái': STATE_LABELS[state],
            'Mã AIS mẫu': str(matches[i]) if i in matches else 'Chưa ghép',
            'Khoảng cách (m)': round(distances[i], 1) if i in distances else None,
            'Lý do': explanation,
            'Xác minh nghiệp vụ': 'Chờ người có chuyên môn',
        })
    return rows, dict(dataset_type='synthetic_demo', scenario=kind,
        age_s=age_s, sigma_m=sigma_m, thresholds=vars(cfg.fusion),
        states=states, reasons=reasons, matches=matches,
        sar_east_m=positions, ais_east_m=positions_ais,
        operational_assessment=pending_review())


CASE_DETAILS = {
    'missing': 'Ảnh SAR có điểm cần rà nhưng không có bản tin AIS cùng thời điểm.',
    'distant': 'Mốc AIS cách điểm SAR khoảng 700 m, ngoài phạm vi ghép.',
    'conflict': 'Vị trí gần nhau. Chiều dài ước lượng từ SAR là 80 m, còn AIS khai báo 200 m.',
    'missing_size': 'Có thể ghép vị trí nhưng bản tin AIS thiếu chiều dài để đối chiếu.',
    'stale': 'Mốc AIS gần điểm SAR. Tuổi bản tin mặc định là 600 giây.',
    'stale_nearby': 'AIS 100 ở gần nhất nhưng mặc định đã cũ. AIS 101 mới hơn ở cách 80 m. Khi từ chối AIS 100, bộ ghép giữ ca để rà.',
    'crossing': 'Hai vị trí SAR gần nhau và có hai bản tin AIS cạnh tranh.',
    'bias': 'Hai chuỗi AIS bị dịch 160 m về hai hướng ngược nhau. Cặp gần nhất có thể đã đổi.',
    'clean': 'Điểm SAR và mốc AIS cách nhau khoảng 3 m. Hai nguồn đều cho chiều dài 80 m.',
}


def export_grid():
    """Materialize deterministic samples, including both sides of each gate."""
    config = RunConfig().fusion
    time_limit = int(config.max_ais_age_s)
    sigma_limit = int(config.max_position_sigma_m)
    ages = sorted({10, time_limit - 1, time_limit, time_limit + 1, 600})
    sigmas = sorted({20, sigma_limit - 1, sigma_limit, sigma_limit + 1, 300})
    cases = {}
    for label, kind in SCENARIOS.items():
        default_age = 600 if kind in {'stale', 'stale_nearby'} else 10
        choices = [(default_age, 20)] if kind == 'missing' else list(product(ages, sigmas))
        samples = {}
        for age, sigma in choices:
            rows, payload = run_scenario(kind, age, float(sigma))
            samples[f'{age}:{sigma}'] = {'rows': rows, 'payload': payload}
        cases[kind] = {
            'label': label,
            'description': CASE_DETAILS[kind],
            'default_age': default_age,
            'samples': samples,
        }
    return {
        'age_options_s': ages,
        'sigma_options_m': sigmas,
        'thresholds': vars(config),
        'cases': cases,
    }


if __name__ == '__main__':
    print(json.dumps(export_grid(), ensure_ascii=False, allow_nan=False))

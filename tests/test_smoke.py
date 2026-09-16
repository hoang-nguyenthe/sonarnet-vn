"""Kiểm thử nhanh toàn bộ các thành phần của SonarNet-VN.

Bộ kiểm thử này chạy được trên CPU trong khoảng một phút và không cần kết nối
mạng. Mục đích là phát hiện sớm lỗi ở từng tầng trước khi khởi động một lần chạy
huấn luyện dài.

Chạy bằng lệnh::

    python -m pytest tests/ -v
    # hoặc, khi không có pytest:
    python tests/test_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sonarnet.config import RunConfig  # noqa: E402
from sonarnet.utils import set_seed  # noqa: E402


def _tiny_config(tmp: Path) -> RunConfig:
    cfg = RunConfig()
    cfg.root = tmp
    cfg.seed = 1234
    cfg.data.scene_size = 256
    cfg.data.n_train_scenes = 6
    cfg.data.n_val_scenes = 3
    cfg.data.n_test_scenes = 4
    cfg.data.ships_per_scene = (3, 7)
    cfg.behavior.n_tracks_per_class = 24
    cfg.behavior.track_hours = 6.0
    cfg.make_dirs()
    return cfg


# ---------------------------------------------------------------------------
def test_geo_roundtrip():
    """Chuyển đổi điểm ảnh sang toạ độ địa lý và ngược lại phải nhất quán."""
    from sonarnet.data.geo import SceneGeoReference

    g = SceneGeoReference(lat_top=10.0, lon_left=108.5, width=640, height=640,
                          pixel_spacing_m=10.0)
    for x, y in [(0, 0), (320, 320), (639, 639), (100, 500)]:
        lon, lat = g.pixel_to_lonlat(x, y)
        x2, y2 = g.lonlat_to_pixel(lon, lat)
        assert abs(float(x2) - x) < 1e-3, f"sai lệch trục x tại ({x}, {y})"
        assert abs(float(y2) - y) < 1e-3, f"sai lệch trục y tại ({x}, {y})"
    print("  ✔ chuyển đổi toạ độ nhất quán")


def test_haversine():
    """Khoảng cách vòng lớn phải khớp với giá trị đã biết."""
    from sonarnet.data.geo import haversine_m

    # Một độ vĩ tuyến xấp xỉ 111 km
    d = float(haversine_m(10.0, 108.0, 11.0, 108.0))
    assert 110_000 < d < 112_000, f"khoảng cách bất thường: {d:.0f} m"
    assert float(haversine_m(10.0, 108.0, 10.0, 108.0)) < 1e-6
    print(f"  ✔ khoảng cách một độ vĩ tuyến: {d:,.0f} m")


def test_sar_render():
    """Bộ dựng ảnh phải trả về ảnh 8 bit đúng kích thước và có tương phản."""
    from sonarnet.data.sar_render import SARRenderer, ShipFootprint

    rng = np.random.default_rng(0)
    r = SARRenderer(size=256)
    ships = [
        ShipFootprint(cx=80, cy=80, length_px=20, width_px=5,
                      heading_deg=30, rcs=5.0, moving=True),
        ShipFootprint(cx=180, cy=150, length_px=12, width_px=3,
                      heading_deg=100, rcs=4.0, moving=False),
    ]
    img, mask = r.render(ships, rng, with_land=False)
    assert img.shape == (256, 256), "kích thước ảnh sai"
    assert img.dtype == np.uint8, "kiểu dữ liệu ảnh sai"
    assert img.std() > 5, "ảnh không có tương phản"
    # Vùng có tàu phải sáng hơn nền rõ rệt
    ship_patch = img[70:90, 70:90].mean()
    sea_patch = img[10:30, 200:220].mean()
    assert ship_patch > sea_patch, "phương tiện không nổi bật so với nền biển"
    print(f"  ✔ ảnh SAR: tàu {ship_patch:.0f} so với nền {sea_patch:.0f}")


def test_simulator_and_dataset(tmp: Path):
    """Sinh dữ liệu và ghi ra đĩa phải tạo đủ tệp với nội dung hợp lệ."""
    from sonarnet.data.dataset import build_dataset, read_ais, read_scene_meta
    from sonarnet.data.simulator import DARK

    cfg = _tiny_config(tmp)
    rng = set_seed(cfg.seed)
    summary = build_dataset(cfg, rng)

    assert len(summary["splits"]) == 3
    assert Path(summary["data_yaml"]).exists(), "thiếu tệp data.yaml"

    meta = read_scene_meta(cfg.dir_yolo, "test")
    assert len(meta) == cfg.data.n_test_scenes
    assert all("vessels" in m and "georef" in m for m in meta)

    ais = read_ais(cfg.dir_yolo, "test")
    total_vessels = sum(len(m["vessels"]) for m in meta)
    dark = sum(
        1 for m in meta for v in m["vessels"] if v["identity_state"] == DARK
    )
    assert total_vessels > 0, "không sinh được phương tiện nào"
    assert dark > 0, "không có phương tiện ngắt định danh nào"

    # Phương tiện ngắt định danh tuyệt đối không được xuất hiện trong dòng AIS
    for m in meta:
        dark_mmsi = {
            v["mmsi"] for v in m["vessels"] if v["identity_state"] == DARK
        }
        ais_mmsi = {int(r["mmsi"]) for r in ais.get(m["scene_id"], [])}
        assert not (dark_mmsi & ais_mmsi), "rò rỉ tín hiệu AIS của phương tiện DARK"

    print(f"  ✔ dữ liệu: {total_vessels} phương tiện, {dark} ngắt định danh")
    return cfg, meta, ais


def test_kalman(cfg, meta, ais):
    """Bộ lọc Kalman phải cho sai số nội suy nhỏ hơn ngưỡng ghép cặp."""
    from sonarnet.data.geo import haversine_m
    from sonarnet.data.simulator import DARK
    from sonarnet.fusion.kalman import ConstantVelocityKalman

    kf = ConstantVelocityKalman(
        process_noise=cfg.fusion.kalman_process_noise,
        measurement_noise=cfg.fusion.kalman_measurement_noise,
    )
    errors = []
    for m in meta:
        t = float(m["capture_time_s"])
        recs = ais.get(m["scene_id"], [])
        by_mmsi = {}
        for r in recs:
            by_mmsi.setdefault(int(r["mmsi"]), []).append(r)
        for v in m["vessels"]:
            if v["identity_state"] == DARK:
                continue
            rs = by_mmsi.get(int(v["mmsi"]))
            if not rs:
                continue
            est = kf.smooth_to_time(rs, t)
            assert est is not None
            errors.append(float(haversine_m(v["lat"], v["lon"], est.lat, est.lon)))

    assert errors, "không có trường hợp nào để đánh giá"
    median = float(np.median(errors))
    assert median < cfg.fusion.max_match_distance_m, (
        f"sai số nội suy trung vị {median:.0f} m vượt ngưỡng ghép cặp"
    )
    print(f"  ✔ Kalman: sai số trung vị {median:.0f} m")


def test_fusion_with_perfect_detections(cfg, meta, ais):
    """Với phát hiện hoàn hảo, tầng hợp nhất phải phân loại trạng thái tốt."""
    from sonarnet.pipeline import run_fusion_records

    # Giả lập bộ phát hiện lý tưởng: dùng chính khung bao đối chứng
    detections = {}
    for m in meta:
        boxes = np.array([v["bbox"] for v in m["vessels"]], dtype=np.float32)
        scores = np.ones(len(boxes), dtype=np.float32)
        detections[m["scene_id"]] = (boxes, scores)

    records = run_fusion_records(cfg, meta, ais, detections,
                                 use_kalman=True, use_size_check=True)
    assert records, "không sinh được bản ghi nào"

    visible = [r for r in records if r["pred_state"] is not None]
    assert len(visible) == sum(len(m["vessels"]) for m in meta), \
        "phát hiện lý tưởng phải phủ toàn bộ phương tiện"

    correct = sum(1 for r in visible if r["pred_state"] == r["true_state"])
    acc = correct / len(visible)
    assert acc > 0.80, f"độ chính xác trạng thái quá thấp: {acc:.2%}"
    print(f"  ✔ hợp nhất: độ chính xác ba trạng thái {acc:.2%}")


def test_behaviour(tmp: Path):
    """Bộ phân loại hành vi phải vượt xa mức đoán ngẫu nhiên."""
    from sonarnet.behavior.classifier import train_and_evaluate
    from sonarnet.behavior.features import FEATURE_NAMES, features_matrix
    from sonarnet.data.tracks import generate_track_dataset

    cfg = _tiny_config(tmp / "behaviour")
    rng = set_seed(cfg.seed)
    tracks = generate_track_dataset(cfg, rng)
    X, y = features_matrix(tracks)

    assert X.shape[1] == len(FEATURE_NAMES), "số đặc trưng không khớp"
    assert np.all(np.isfinite(X)), "ma trận đặc trưng chứa giá trị không hợp lệ"

    _, report = train_and_evaluate(X, y, FEATURE_NAMES, cfg)
    assert report.macro_f1 > 0.55, f"F1 vĩ mô quá thấp: {report.macro_f1:.3f}"
    print(f"  ✔ hành vi: F1 vĩ mô {report.macro_f1:.3f} ({report.backend})")


def test_detection_metrics():
    """Chỉ tiêu phát hiện phải đúng trên các trường hợp đã biết đáp án."""
    from sonarnet.evaluation.detection_metrics import box_iou, evaluate_detections

    a = np.array([[0, 0, 10, 10]], dtype=np.float32)
    b = np.array([[0, 0, 10, 10], [20, 20, 30, 30]], dtype=np.float32)
    iou = box_iou(a, b)
    assert abs(iou[0, 0] - 1.0) < 1e-5, "IoU của hai khung trùng nhau phải bằng 1"
    assert iou[0, 1] < 1e-5, "IoU của hai khung rời nhau phải bằng 0"

    gt = {"x": np.array([[0, 0, 10, 10], [20, 20, 30, 30]], dtype=np.float32)}
    pred = {"x": (gt["x"].copy(), np.array([0.9, 0.8], dtype=np.float32))}
    m = evaluate_detections(pred, gt)
    assert m.recall == 1.0 and m.precision == 1.0, "dự đoán hoàn hảo phải đạt tối đa"
    assert m.ap50 > 0.99, f"mAP phải xấp xỉ 1, nhận được {m.ap50:.3f}"
    print("  ✔ chỉ tiêu phát hiện chính xác trên trường hợp kiểm chứng")


def test_ablation_logic(cfg, meta, ais):
    """Bảng phân tích đóng góp phải phản ánh đúng bản chất từng cấu hình."""
    from sonarnet.evaluation.ablation import run_ablation
    from sonarnet.pipeline import run_fusion_records

    detections = {}
    for m in meta:
        boxes = np.array([v["bbox"] for v in m["vessels"]], dtype=np.float32)
        detections[m["scene_id"]] = (boxes, np.ones(len(boxes), dtype=np.float32))

    rows, _ = run_ablation(run_fusion_records, cfg, meta, ais, detections)
    by_cfg = {r.config: r for r in rows}
    assert set(by_cfg) == {"A", "B", "C", "D"}, "thiếu cấu hình so sánh"

    # Chỉ dùng AIS thì không thể phát hiện phương tiện ngắt định danh
    assert by_cfg["B"].dark_recall < 1e-6, "cấu hình B không được phát hiện DARK"
    # Hệ thống đầy đủ phải vượt trội cấu hình chỉ dùng AIS về lớp DARK
    assert by_cfg["D"].dark_f1 > by_cfg["B"].dark_f1, "hợp nhất phải cải thiện lớp DARK"
    # Chỉ dùng ảnh radar thì gán tất cả là DARK nên độ chính xác lớp này rất thấp
    assert by_cfg["A"].dark_precision < by_cfg["D"].dark_precision, \
        "hợp nhất phải cải thiện độ chính xác lớp DARK"

    print(f"  ✔ ablation: F1 lớp DARK — A {by_cfg['A'].dark_f1:.3f} | "
          f"B {by_cfg['B'].dark_f1:.3f} | C {by_cfg['C'].dark_f1:.3f} | "
          f"D {by_cfg['D'].dark_f1:.3f}")


def main() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="sonarnet_test_"))
    print(f"Thư mục tạm: {tmp}\n")
    failures = 0

    try:
        print("1. Hệ toạ độ")
        test_geo_roundtrip()
        test_haversine()

        print("\n2. Dựng ảnh radar")
        test_sar_render()

        print("\n3. Sinh dữ liệu")
        cfg, meta, ais = test_simulator_and_dataset(tmp / "data")

        print("\n4. Nội suy quỹ đạo")
        test_kalman(cfg, meta, ais)

        print("\n5. Hợp nhất radar và AIS")
        test_fusion_with_perfect_detections(cfg, meta, ais)

        print("\n6. Chỉ tiêu phát hiện")
        test_detection_metrics()

        print("\n7. Phân tích đóng góp thành phần")
        test_ablation_logic(cfg, meta, ais)

        print("\n8. Phân loại hành vi")
        test_behaviour(tmp)

    except AssertionError as exc:
        print(f"\n✘ KIỂM THỬ THẤT BẠI: {exc}")
        failures += 1
    except Exception as exc:  # pragma: no cover
        import traceback

        print(f"\n✘ LỖI KHÔNG MONG ĐỢI: {exc}")
        traceback.print_exc()
        failures += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures == 0:
        print("\n" + "=" * 62)
        print("TOÀN BỘ KIỂM THỬ ĐÃ ĐẠT — mã nguồn sẵn sàng để chạy trên Kaggle.")
        print("=" * 62)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())

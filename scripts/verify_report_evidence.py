"""Verify the experiment artifacts cited by the Eureka report.

The script intentionally reads existing result files rather than re-computing a
model run.  It checks arithmetic consistency, records provenance, and writes a
small JSON certificate that can be cited alongside the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


RESULT_FILES = {
    "detection": "detection_metrics_test.json",
    "fusion": "fusion_metrics.json",
    "interpolation": "interpolation_comparison.json",
    "behavior": "behavior_metrics.json",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp kết quả: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _close(actual: float, expected: float, tolerance: float = 1e-4) -> bool:
    return abs(float(actual) - float(expected)) <= tolerance


def verify_results(root: Path) -> dict[str, Any]:
    """Validate result artifacts under ``root/results`` and return a certificate."""
    results_dir = root / "results"
    artifacts = {key: results_dir / name for key, name in RESULT_FILES.items()}
    payload = {key: _read_json(path) for key, path in artifacts.items()}

    det = payload["detection"]
    tp, fp, fn = (int(det["true_positive"]), int(det["false_positive"]), int(det["false_negative"]))
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)
    detection_ok = (
        _close(det["precision"], precision)
        and _close(det["recall"], recall)
        and _close(det["f1"], f1)
        and int(det["n_ground_truth"]) == tp + fn
        and int(det["n_predictions"]) == tp + fp
    )

    fusion = payload["fusion"]
    labels = fusion["confusion_labels"]
    matrix = fusion["confusion_matrix"]
    if len(labels) != 3 or len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise ValueError("Ma trận hợp nhất phải có đúng 3 lớp và 3 hàng, 3 cột.")
    n_matrix = sum(sum(int(value) for value in row) for row in matrix)
    fusion_ok = n_matrix == int(fusion["n_evaluated"]) and _close(
        fusion["state_accuracy"], sum(int(matrix[i][i]) for i in range(3)) / n_matrix
    )

    interpolation = payload["interpolation"]
    interpolation_ok = (
        int(interpolation["kalman"]["n"]) == int(interpolation["linear"]["n"])
        and float(interpolation["kalman"]["mean_error_m"])
        < float(interpolation["linear"]["mean_error_m"])
        and float(interpolation["kalman"]["p90_error_m"])
        < float(interpolation["linear"]["p90_error_m"])
    )

    behavior = payload["behavior"]
    behavior_ok = int(behavior["n_test"]) == sum(sum(int(v) for v in row) for row in behavior["confusion_matrix"])

    project_root = root.parent
    real_eval_path = project_root / "assets" / "real_model_evaluation.json"
    coverage_path = project_root / "assets" / "real_scan" / "coverage.json"
    scan_report_path = project_root / "assets" / "real_scan" / "report.json"
    real_eval = _read_json(real_eval_path)
    coverage = _read_json(coverage_path)
    scan_report = _read_json(scan_report_path)

    benchmark = real_eval["benchmark"]
    real_model_ok = (
        real_eval["model_status"] == "research_candidate_not_promoted"
        and int(benchmark["images"]) > 0
        and int(benchmark["objects"]) > 0
        and all(0.0 <= float(benchmark[key]) <= 1.0 for key in ("precision", "recall", "map50", "map50_95"))
    )
    vietnam = next(region for region in coverage["regions"] if region["key"] == "vietnam")
    processed_tiles = len(scan_report["tiles"])
    detected_candidates = sum(len(tile.get("detections", [])) for tile in scan_report["tiles"])
    coverage_ok = (
        int(vietnam["published_detail_cells"]) == processed_tiles
        and all(tile.get("status") == "processed" for tile in scan_report["tiles"])
        and scan_report["limitations"]
    )

    checks = {
        "detection_arithmetic": detection_ok,
        "fusion_matrix": fusion_ok,
        "interpolation_comparison": interpolation_ok,
        "behavior_matrix": behavior_ok,
        "real_model_candidate_metadata": real_model_ok,
        "published_coverage_consistency": bool(coverage_ok),
    }
    certificate = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "scope": "Kiểm tra tính nhất quán của tệp kết quả đã có; không phải đánh giá độc lập trên dữ liệu thực địa.",
        "artifacts": {key: {"path": str(path), "sha256": _sha256(path)} for key, path in artifacts.items()},
        "summary": {
            "detection": {key: det[key] for key in ("mAP@0.5", "mAP@0.5:0.95", "precision", "recall", "f1", "n_ground_truth", "n_predictions", "true_positive", "false_positive", "false_negative")},
            "fusion": {key: fusion[key] for key in ("match_accuracy", "mean_match_error_m", "median_match_error_m", "p90_match_error_m", "state_accuracy", "state_macro_f1", "n_evaluated")},
            "interpolation": interpolation,
            "behavior": {key: behavior[key] for key in ("backend", "accuracy", "macro_f1", "n_train", "n_test")},
            "real_model_candidate": {
                "status": real_eval["model_status"],
                "benchmark": benchmark,
                "real_vietnam_check": real_eval["real_vietnam_check"],
                "promotion_decision": real_eval["promotion_decision"],
            },
            "published_vietnam_scan": {
                "cells": processed_tiles,
                "candidates": detected_candidates,
                "latest_detail_day_utc": vietnam["latest_detail_day_utc"],
                "states": vietnam["states"],
                "limitations": scan_report["limitations"],
            },
        },
    }
    certificate["artifacts"].update({
        "real_model_evaluation": {"path": str(real_eval_path), "sha256": _sha256(real_eval_path)},
        "coverage": {"path": str(coverage_path), "sha256": _sha256(coverage_path)},
        "real_scan_report": {"path": str(scan_report_path), "sha256": _sha256(scan_report_path)},
    })
    return certificate


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra tính nhất quán số liệu dùng trong báo cáo SonarNet.")
    parser.add_argument("--root", type=Path, default=Path("sonarnet_run"), help="Thư mục chứa results.")
    parser.add_argument("--out", type=Path, default=Path("sonarnet_run/results/report_evidence.json"), help="Tệp chứng nhận JSON.")
    args = parser.parse_args()
    certificate = verify_results(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(certificate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": certificate["status"], "checks": certificate["checks"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if certificate["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

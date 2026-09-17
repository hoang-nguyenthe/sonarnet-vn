import json
from pathlib import Path

from scripts.verify_report_evidence import verify_results


def test_existing_report_artifacts_are_consistent():
    root = Path(__file__).resolve().parents[1] / "sonarnet_run"
    certificate = verify_results(root)
    assert certificate["status"] == "passed"
    assert all(certificate["checks"].values())
    assert certificate["summary"]["detection"]["true_positive"] == 643
    assert certificate["summary"]["fusion"]["n_evaluated"] == 652
    assert certificate["summary"]["real_model_candidate"]["status"] == "research_candidate_not_promoted"
    assert certificate["summary"]["real_model_candidate"]["benchmark"]["images"] == 1953
    assert certificate["summary"]["published_vietnam_scan"]["cells"] == 1490
    assert certificate["summary"]["published_vietnam_scan"]["candidates"] == 1196


def test_certificate_is_json_serializable():
    root = Path(__file__).resolve().parents[1] / "sonarnet_run"
    certificate = verify_results(root)
    assert json.loads(json.dumps(certificate, ensure_ascii=False))["status"] == "passed"

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
    # Published coverage grows independently of the historical research run.
    # Check the certificate against its source manifest instead of an old count.
    scan=json.loads((root.parent/'assets/real_scan/report.json').read_text())
    assert certificate["summary"]["published_vietnam_scan"]["cells"] == len(scan['tiles'])
    assert certificate["summary"]["published_vietnam_scan"]["candidates"] == sum(len(t.get('detections',[])) for t in scan['tiles'])


def test_certificate_is_json_serializable():
    root = Path(__file__).resolve().parents[1] / "sonarnet_run"
    certificate = verify_results(root)
    assert json.loads(json.dumps(certificate, ensure_ascii=False))["status"] == "passed"

"""Bounded browser check of the public app; never runs inference or writes data."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

APP_URL = "https://sonarnet.streamlit.app/"
EVIDENCE_LINK = "?trang=minh-chung"
ROOT = Path(__file__).resolve().parents[1]
REPORT_PDF = ROOT / "output/pdf/SonarNet_Bao_cao_Chang1_20261120.pdf"
SAMPLE_ZIP = ROOT / "reports/final/export_verification/sample_evidence.zip"
REPORT_DOWNLOAD = "Tải báo cáo nộp Chặng 1 · 20 trang"
SAMPLE_TOGGLE = "Mở hồ sơ ảnh SAR thật thiếu AIS"
SAMPLE_DOWNLOAD = "Tải ZIP ảnh và hồ sơ mẫu"
RECALL_LINK = "?trang=minh-chung&muc=recall"
RECALL_HEADING = "Đối chứng recall trên ảnh Sentinel-1"
RECALL_DOWNLOAD = "Tải kết quả thử radar hai kênh"
RECALL_SUMMARY = ROOT / "reports/final/vietnam_rtc_transfer_20261119/summary.json"
RANK_TOGGLE = "Xếp hạng theo đồng thuận YOLO và xView3"
RANK_DOWNLOAD = "Tải số liệu thử gộp thứ hạng"
RANK_RESULTS = RECALL_SUMMARY.parent / "rank_fusion/results.json"
AIS_RANK_DOWNLOAD = "Tải đối chứng gộp hạng trên sáu cảnh AIS"
AIS_RANK_RESULTS = RANK_RESULTS.parent / "ais-holdout/results.json"
WAKE_BUTTON = "Yes, get this app back up!"
READY_HEADING = re.compile(r"Đọc tín hiệu biển", re.IGNORECASE)


class HealthCheckError(RuntimeError):
    pass


class StreamlitConnection:
    def __init__(self):
        self.messages = 0
        self.active = set()

    def opened(self, socket):
        parsed = urlsplit(socket.url)
        if parsed.hostname != "sonarnet.streamlit.app" or not parsed.path.endswith("/_stcore/stream"):
            return
        key = id(socket)
        self.active.add(key)
        socket.on("framereceived", lambda _payload: self.received())
        socket.on("close", lambda: self.active.discard(key))

    def received(self):
        # Count only: never save websocket payloads, cookies or browser state.
        self.messages += 1

    @property
    def live(self):
        return bool(self.active) and self.messages > 0


def classify_error(text):
    lowered = text.casefold()
    for needle, reason in (
        ("this app has gone over its resource limits", "resource_limit"),
        ("error running app", "app_error"),
        ("you do not have access to this app", "access_denied"),
    ):
        if needle in lowered:
            return reason
    return None


def inspect_page(page, *, evidence=False, recall=False):
    """Inspect both Community Cloud's wrapper and the actual Streamlit frame."""
    ready = False
    wake = None
    for frame in page.frames:
        if urlsplit(frame.url).hostname != "sonarnet.streamlit.app":
            continue
        try:
            if frame.is_detached():
                continue
            error = classify_error(frame.locator("body").inner_text(timeout=1500))
            if error:
                raise HealthCheckError(error)
            if frame.locator('[data-testid="stException"]').count():
                raise HealthCheckError("streamlit_exception")
            button = frame.get_by_role("button", name=WAKE_BUTTON, exact=True)
            if button.is_visible():
                wake = button
            if recall:
                ready = ready or (
                    frame.get_by_role("heading", name=RECALL_HEADING, exact=True).is_visible()
                    and frame.get_by_role("button", name=RECALL_DOWNLOAD, exact=True).is_visible()
                )
            elif evidence:
                ready = ready or all(frame.get_by_text(marker, exact=True).first.is_visible() for marker in (
                    "Kết quả trước và sau cải tiến", "Kiểm tra thêm cách đọc SAR ở hai tỷ lệ",
                    "Kiểm tra trên ảnh ven biển Việt Nam", "Huấn luyện ở 640 px giữ thêm mục tiêu",
                    "Recall trên 12 lượt chụp mới", REPORT_DOWNLOAD,
                    "Bảng đầy đủ và các bộ xếp hạng",
                    "Xem ảnh radar thật và các điểm được tìm thêm",
                    "Thử xếp hạng bằng hai kênh radar VV và VH", "Mở hồ sơ ảnh SAR thật thiếu AIS",
                    "Kiểm tra lỗi đổi đối tác sau khi lọc AIS",
                    "Xem cảnh Sentinel-1 và AIS cùng lượt chụp",
                ))
            elif (frame.get_by_role("heading", name=READY_HEADING).is_visible()
                    and frame.get_by_text("Quan sát", exact=True).first.is_visible()):
                ready = True
        except HealthCheckError:
            raise
        except Exception:
            # Frame replacement/navigation is normal while a sleeping app boots.
            continue
    return ready, wake


def wait_for_app(page, connection, report, timeout_seconds=420,
                 inspect=inspect_page, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout_seconds
    stable_since = None
    last_wake = -1000.0
    while clock() < deadline:
        ready, wake = inspect(page)
        now = clock()
        if wake is not None and report["wake_clicks"] < 2 and now - last_wake >= 60:
            wake.click(timeout=5000)
            report["wake_clicks"] += 1
            last_wake = now
            stable_since = None
        elif ready and connection.live:
            if stable_since is None:
                stable_since = now
            if now - stable_since >= 10:
                return
        else:
            stable_since = None
        sleep(2)
    raise HealthCheckError("app_not_ready_before_deadline")


def verify_download(page, label, expected_sha, field):
    for frame in page.frames:
        if urlsplit(frame.url).hostname != "sonarnet.streamlit.app" or frame.is_detached():
            continue
        button = frame.get_by_role("button", name=label, exact=True)
        if button.is_visible():
            with page.expect_download(timeout=30000) as receipt:
                button.click(timeout=10000)
            actual_sha = sha256(receipt.value.path().read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise HealthCheckError(f"{field}_payload_differs_from_release")
            return actual_sha
    raise HealthCheckError(f"{field}_download_control_missing")


def verify_recall_download(page, expected_sha):
    return verify_download(page, RECALL_DOWNLOAD, expected_sha, "recall")


def open_download_panel(page, label, download_label, field):
    for frame in page.frames:
        if urlsplit(frame.url).hostname != "sonarnet.streamlit.app" or frame.is_detached():
            continue
        toggle = frame.get_by_text(label, exact=True).first
        if toggle.is_visible():
            toggle.click(timeout=10000)
            frame.get_by_role("button", name=download_label, exact=True).wait_for(
                state="visible", timeout=20000
            )
            return
    raise HealthCheckError(f"{field}_toggle_missing")


def verify_rank_download(page):
    open_download_panel(page, RANK_TOGGLE, RANK_DOWNLOAD, "rank")
    return verify_download(page, RANK_DOWNLOAD, sha256(RANK_RESULTS.read_bytes()).hexdigest(), "rank")


def verify_submission_downloads(page, report):
    """Exercise the judge's public report and evidence downloads."""
    report["pdf_sha256"] = verify_download(
        page, REPORT_DOWNLOAD, sha256(REPORT_PDF.read_bytes()).hexdigest(), "pdf"
    )
    open_download_panel(page, SAMPLE_TOGGLE, SAMPLE_DOWNLOAD, "sample")
    report["sample_zip_sha256"] = verify_download(
        page, SAMPLE_DOWNLOAD, sha256(SAMPLE_ZIP.read_bytes()).hexdigest(), "sample"
    )


def write_report(output, report):
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## SonarNet browser availability check\n\n")
            for key in ("mode", "status", "checked_at", "elapsed_seconds", "wake_clicks",
                        "websocket_messages", "pdf_sha256", "sample_zip_sha256",
                        "recall_sha256", "rank_sha256", "ais_rank_sha256", "error"):
                if key in report:
                    handle.write(f"- {key}: {report[key]}\n")
            handle.write("\nPassing means the app rendered and the Streamlit connection stayed active at this check, not continuous uptime.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/web-health"))
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--evidence", action="store_true", help="Require the Chặng 1 evidence page and report control.")
    target.add_argument("--recall", action="store_true", help="Verify the public recall page and its exact release JSON.")
    target.add_argument("--submission", action="store_true", help="Verify the judge's page and exact PDF and sample ZIP.")
    parser.add_argument("--chromium-executable", type=Path, help="Optional installed Chromium or Chrome executable.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = args.evidence or args.submission
    suffix = RECALL_LINK if args.recall else EVIDENCE_LINK if evidence else ""
    mode = "submission" if args.submission else "recall" if args.recall else "chang1_evidence" if evidence else "homepage"
    report = {
        "url": APP_URL + suffix,
        "mode": mode,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "event": os.environ.get("GITHUB_EVENT_NAME"),
        "status": "failed",
        "wake_clicks": 0,
    }
    connection = StreamlitConnection()
    started = time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium_executable)
            context = browser.new_context(viewport={"width": 1365, "height": 900}, locale="en-US", accept_downloads=True)
            page = context.new_page()
            page.on("websocket", connection.opened)
            try:
                page.goto(report["url"], wait_until="domcontentloaded", timeout=60000)
                # Playwright's wait pumps websocket events; time.sleep would not.
                wait_for_app(page, connection, report,
                             inspect=lambda active: inspect_page(active, evidence=evidence, recall=args.recall),
                             sleep=lambda seconds: page.wait_for_timeout(seconds * 1000))
                if args.recall:
                    expected_sha = sha256(RECALL_SUMMARY.read_bytes()).hexdigest()
                    report["recall_sha256"] = verify_recall_download(page, expected_sha)
                    report["rank_sha256"] = verify_rank_download(page)
                    if AIS_RANK_RESULTS.is_file():
                        report["ais_rank_sha256"] = verify_download(
                            page, AIS_RANK_DOWNLOAD, sha256(AIS_RANK_RESULTS.read_bytes()).hexdigest(), "ais_rank"
                        )
                if args.submission:
                    verify_submission_downloads(page, report)
                report["status"] = "healthy"
                if args.evidence:
                    for frame in page.frames:
                        result = frame.get_by_role("heading", name="Recall trên 12 lượt chụp mới", exact=True)
                        if result.count():
                            try:
                                result.scroll_into_view_if_needed(timeout=3000)
                                page.screenshot(path=str(args.output / "recall-vietnam.jpg"),
                                                type="jpeg", quality=80, timeout=10000)
                            except Exception:
                                report["recall_screenshot"] = "unavailable"
                            break
            finally:
                try:
                    page.screenshot(path=str(args.output / "page.jpg"), type="jpeg", quality=70, timeout=10000)
                except Exception:
                    report["screenshot"] = "unavailable"
                context.close()
                browser.close()
    except Exception as exc:
        # Playwright errors can contain URLs/tokens; store only our safe codes.
        report["error"] = str(exc) if isinstance(exc, HealthCheckError) else type(exc).__name__
    report["websocket_messages"] = connection.messages
    report["elapsed_seconds"] = round(time.monotonic() - started, 1)
    write_report(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())

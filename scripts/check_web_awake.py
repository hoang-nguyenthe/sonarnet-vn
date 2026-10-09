"""Bounded browser check of the public app; never runs inference or writes data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

APP_URL = "https://sonarnet.streamlit.app/"
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


def inspect_page(page):
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
            if (frame.get_by_role("heading", name=READY_HEADING).is_visible()
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


def write_report(output, report):
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## SonarNet browser availability check\n\n")
            for key in ("status", "checked_at", "elapsed_seconds", "wake_clicks", "websocket_messages", "error"):
                if key in report:
                    handle.write(f"- {key}: {report[key]}\n")
            handle.write("\nPassing means the app rendered and the Streamlit connection stayed active at this check, not continuous uptime.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/web-health"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "url": APP_URL,
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
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1365, "height": 900}, locale="en-US")
            page = context.new_page()
            page.on("websocket", connection.opened)
            try:
                page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
                # Playwright's wait pumps websocket events; time.sleep would not.
                wait_for_app(page, connection, report, sleep=lambda seconds: page.wait_for_timeout(seconds * 1000))
                report["status"] = "healthy"
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

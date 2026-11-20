import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import unittest

spec = importlib.util.spec_from_file_location("web_health", Path(__file__).resolve().parents[1] / "scripts/check_web_awake.py")
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class Clock:
    now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Button:
    clicks = 0

    def click(self, **kwargs):
        self.clicks += 1


class Socket:
    def __init__(self, url):
        self.url = url
        self.events = {}

    def on(self, event, callback):
        self.events[event] = callback


class WebAwakeTests(unittest.TestCase):
    def run_wait(self, inspect, live=True, timeout=100):
        timer = Clock()
        connection = type("Connection", (), {"live": live})()
        report = {"wake_clicks": 0}
        health.wait_for_app(None, connection, report, timeout_seconds=timeout,
                            inspect=inspect, clock=timer.time, sleep=timer.sleep)
        return report, timer

    def test_ready_app_needs_stable_render(self):
        report, timer = self.run_wait(lambda page: (True, None))
        self.assertEqual(timer.now, 10)
        self.assertEqual(report["wake_clicks"], 0)

    def test_static_html_without_websocket_is_not_healthy(self):
        with self.assertRaisesRegex(health.HealthCheckError, "deadline"):
            self.run_wait(lambda page: (True, None), live=False, timeout=12)

    def test_sleeping_app_wakes_once_then_verifies(self):
        button = Button()
        report, _ = self.run_wait(lambda page: (True, None) if button.clicks else (False, button))
        self.assertEqual(report["wake_clicks"], 1)
        self.assertEqual(button.clicks, 1)

    def test_sleeping_app_has_bounded_wake_attempts(self):
        button = Button()
        with self.assertRaises(health.HealthCheckError):
            self.run_wait(lambda page: (False, button), timeout=200)
        self.assertEqual(button.clicks, 2)

    def test_flickering_ready_marker_does_not_pass(self):
        calls = []
        def inspect(page):
            calls.append(1)
            return len(calls) % 2 == 0, None
        with self.assertRaises(health.HealthCheckError):
            self.run_wait(inspect, timeout=20)

    def test_cloud_error_classification(self):
        self.assertEqual(health.classify_error("Oh no. Error running app."), "app_error")
        self.assertEqual(health.classify_error("This app has gone over its resource limits."), "resource_limit")
        self.assertIsNone(health.classify_error("Your app is in the oven"))

    def test_recall_mode_requires_the_new_heading_and_download_control(self):
        page = MagicMock()
        frame = MagicMock()
        page.frames = [frame]
        frame.url = health.APP_URL + health.RECALL_LINK
        frame.is_detached.return_value = False
        frame.locator.return_value.inner_text.return_value = "Minh chứng cải tiến"
        frame.locator.return_value.count.return_value = 0
        visible = {"Kết quả trước và sau cải tiến"}
        frame.get_by_role.side_effect = lambda role, *, name, exact=False: MagicMock(
            is_visible=lambda: name in visible)
        self.assertEqual(health.inspect_page(page, recall=True), (False, None))
        visible.add(health.RECALL_HEADING)
        self.assertEqual(health.inspect_page(page, recall=True), (False, None))
        visible.add(health.RECALL_DOWNLOAD)
        self.assertEqual(health.inspect_page(page, recall=True), (True, None))

    def test_recall_mode_rejects_an_older_download(self):
        page = MagicMock()
        frame = MagicMock()
        page.frames = [frame]
        frame.url = health.APP_URL + health.RECALL_LINK
        frame.is_detached.return_value = False
        frame.get_by_role.return_value.is_visible.return_value = True
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "summary.json"
            payload.write_bytes(b"current release")
            receipt = page.expect_download.return_value.__enter__.return_value
            receipt.value.path.return_value = payload
            expected = health.sha256(payload.read_bytes()).hexdigest()
            self.assertEqual(health.verify_recall_download(page, expected), expected)
            payload.write_bytes(b"previous release")
            with self.assertRaisesRegex(health.HealthCheckError, "differs_from_release"):
                health.verify_recall_download(page, expected)

    def test_submission_verifies_report_and_sample_after_opening_sample(self):
        page = MagicMock()
        frame = MagicMock()
        page.frames = [frame]
        frame.url = health.APP_URL + health.EVIDENCE_LINK
        frame.is_detached.return_value = False
        toggle = frame.get_by_text.return_value.first
        toggle.is_visible.return_value = True
        with patch.object(health, "verify_download", side_effect=["pdf", "sample"]) as verify:
            result = {}
            health.verify_submission_downloads(page, result)
        self.assertEqual(result, {"pdf_sha256": "pdf", "sample_zip_sha256": "sample"})
        toggle.click.assert_called_once()
        self.assertEqual(
            [(call.args[1], call.args[3]) for call in verify.call_args_list],
            [(health.REPORT_DOWNLOAD, "pdf"), (health.SAMPLE_DOWNLOAD, "sample")],
        )

    def test_only_live_streamlit_socket_counts(self):
        tracker = health.StreamlitConnection()
        unrelated = Socket("wss://example.com/_stcore/stream")
        tracker.opened(unrelated)
        self.assertFalse(unrelated.events)
        socket = Socket("wss://sonarnet.streamlit.app/~/+/_stcore/stream")
        tracker.opened(socket)
        self.assertFalse(tracker.live)
        socket.events["framereceived"](b"not recorded")
        self.assertTrue(tracker.live)
        self.assertEqual(tracker.messages, 1)
        socket.events["close"]()
        self.assertFalse(tracker.live)


if __name__ == "__main__":
    unittest.main()

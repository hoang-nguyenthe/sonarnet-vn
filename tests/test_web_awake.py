import importlib.util
from pathlib import Path
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

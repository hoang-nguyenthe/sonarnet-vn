"""Keep short-lived access tokens in memory only during long data jobs."""
import time


class RefreshingToken:
    def __init__(self, acquire, clock=time.monotonic):
        self.acquire = acquire
        self.clock = clock
        self._token = None
        self._deadline = 0

    def get(self):
        if self._token is None or self.clock() >= self._deadline:
            token, lifetime = self.acquire()
            # Leave time for the in-flight request; short-lived grants use
            # half their life rather than an already-expired deadline.
            margin = min(150, lifetime / 2)
            self._token = token
            self._deadline = self.clock() + lifetime - margin
        return self._token

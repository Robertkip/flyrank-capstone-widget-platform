"""Sliding-window rate limiter (in memory, thread-safe). Keys: per IP and per widget."""
import threading
import time
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: float, now: float | None = None) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds). Only allowed requests are counted."""
        t = now if now is not None else time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= t - window_s:
                q.popleft()
            if len(q) >= limit:
                return False, max(1, int(q[0] + window_s - t) + 1)
            q.append(t)
            return True, 0

    def reset(self):
        with self.lock:
            self.hits.clear()


limiter = SlidingWindow()

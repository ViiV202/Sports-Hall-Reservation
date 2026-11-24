import time
import threading
from collections import deque
from typing import Dict, Tuple


class SlidingWindowRateLimiter:
    """محدودکننده ضد اسپم امن در برابر چندنخی (Sliding Window)"""

    def __init__(self, max_requests: int = 5, window_seconds: float = 5.0, warn_cooldown: float = 5.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.warn_cooldown = warn_cooldown
        self._lock = threading.Lock()
        self._buckets: Dict[int, deque] = {}
        self._last_warn: Dict[int, float] = {}

    def check(self, user_id: int, now: float = None) -> Tuple[bool, bool]:
        """
        بررسی مجاز بودن ارسال پیام توسط کاربر.
        خروجی: (allowed, should_warn)
        """
        ts = time.monotonic() if now is None else now
        cutoff = ts - self.window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(user_id, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                last_w = self._last_warn.get(user_id, -1e9)
                should_warn = (ts - last_w) >= self.warn_cooldown
                if should_warn:
                    self._last_warn[user_id] = ts
                return False, should_warn

            bucket.append(ts)
            return True, False

    def reset_user(self, user_id: int) -> None:
        with self._lock:
            self._buckets.pop(user_id, None)
            self._last_warn.pop(user_id, None)

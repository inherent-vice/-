from __future__ import annotations

import threading
import time

from dart_app import config


class HttpGuard:
    def __init__(self, min_interval=None):
        self.min_interval = config.HTTP_MIN_INTERVAL if min_interval is None else float(min_interval)
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._failures: dict[str, int] = {}
        self._blocked_until: dict[str, float] = {}

    def before_request(self, label):
        label = str(label or "default")
        with self._lock:
            now = time.monotonic()
            blocked_until = self._blocked_until.get(label, 0.0)
            if blocked_until > now:
                wait = int(blocked_until - now)
                raise RuntimeError(f"{label} 요청이 일시 차단되어 있습니다. {wait}초 후 다시 시도하세요.")

            delay = self.min_interval - (now - self._last_request)
            if delay > 0:
                time.sleep(delay)
            self._last_request = time.monotonic()

    def after_success(self, label):
        with self._lock:
            self._failures.pop(str(label or "default"), None)
            self._blocked_until.pop(str(label or "default"), None)

    def after_failure(self, label):
        label = str(label or "default")
        with self._lock:
            failures = self._failures.get(label, 0) + 1
            self._failures[label] = failures
            if failures >= config.CIRCUIT_FAIL_LIMIT:
                self._blocked_until[label] = time.monotonic() + config.CIRCUIT_COOLDOWN

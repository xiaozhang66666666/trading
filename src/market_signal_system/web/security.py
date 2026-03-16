"""Security primitives for web auth."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque

_PBKDF2_PREFIX = "pbkdf2_sha256"
_DEFAULT_ROUNDS = 120_000


def hash_password(password: str, *, rounds: int = _DEFAULT_ROUNDS) -> str:
    raw = str(password or "")
    if not raw:
        raise ValueError("password 不能为空")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, int(rounds))
    return f"{_PBKDF2_PREFIX}${int(rounds)}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        prefix, rounds_raw, salt_hex, digest_hex = str(stored_hash).split("$", 3)
    except ValueError:
        return False
    if prefix != _PBKDF2_PREFIX:
        return False
    try:
        rounds = int(rounds_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False
    test = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, rounds)
    return hmac.compare_digest(test, expected)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


class LoginRateLimiter:
    """In-memory sliding-window limiter for failed login attempts."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        window_seconds: int = 300,
    ) -> None:
        if int(max_attempts) < 1:
            raise ValueError("max_attempts must be >= 1")
        if int(window_seconds) < 1:
            raise ValueError("window_seconds must be >= 1")
        self.max_attempts = int(max_attempts)
        self.window_seconds = int(window_seconds)
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now_ts: float) -> deque[float]:
        queue = self._events.get(key)
        if queue is None:
            queue = deque()
            self._events[key] = queue
        cutoff = now_ts - float(self.window_seconds)
        while queue and queue[0] <= cutoff:
            queue.popleft()
        return queue

    def is_allowed(self, key: str) -> bool:
        now_ts = time.time()
        with self._lock:
            queue = self._prune(str(key), now_ts)
            return len(queue) < self.max_attempts

    def register_failure(self, key: str) -> None:
        now_ts = time.time()
        with self._lock:
            queue = self._prune(str(key), now_ts)
            queue.append(now_ts)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(str(key), None)

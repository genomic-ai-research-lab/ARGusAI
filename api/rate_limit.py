"""Simple in-memory API rate limiting utilities."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
import time

from fastapi import HTTPException

from config import settings

_WINDOW_SECONDS = 60
_lock = Lock()
_request_times: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(key: str) -> None:
    """Raise 429 if the per-minute limit is exceeded for a key."""

    now = time.time()
    with _lock:
        bucket = _request_times[key]
        while bucket and now - bucket[0] >= _WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= settings.API_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(status_code=429, detail="API rate limit exceeded. Please retry shortly.")

        bucket.append(now)

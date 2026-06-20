"""A tiny async-safe TTL + LRU cache for extraction results.

Repeated extractions of the same URL are common (user retries, re-pastes).
Caching the parsed result turns a multi-second yt-dlp run into an instant hit.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, *, ttl: int, max_entries: int) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._store: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._ttl > 0 and self._max > 0

    async def get(self, key: str) -> T | None:
        if not self.enabled:
            return None
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: T) -> None:
        if not self.enabled:
            return
        async with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

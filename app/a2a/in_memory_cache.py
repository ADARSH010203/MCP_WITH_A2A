"""Small thread-safe in-memory cache used by the A2A layer."""

import threading
import time
from typing import Any


class InMemoryCache:
    """Thread-safe singleton cache with optional TTL support."""

    _instance: "InMemoryCache | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "InMemoryCache":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache_data = {}
                    cls._instance._ttl = {}
                    cls._instance._data_lock = threading.Lock()
        return cls._instance

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._data_lock:
            self._cache_data[key] = value
            if ttl is None:
                self._ttl.pop(key, None)
            else:
                self._ttl[key] = time.monotonic() + max(0, ttl)

    def get(self, key: str, default: Any = None) -> Any:
        with self._data_lock:
            expires_at = self._ttl.get(key)
            if expires_at is not None and time.monotonic() >= expires_at:
                self._cache_data.pop(key, None)
                self._ttl.pop(key, None)
                return default
            return self._cache_data.get(key, default)

    def delete(self, key: str) -> bool:
        with self._data_lock:
            existed = key in self._cache_data
            self._cache_data.pop(key, None)
            self._ttl.pop(key, None)
            return existed

    def clear(self) -> None:
        with self._data_lock:
            self._cache_data.clear()
            self._ttl.clear()

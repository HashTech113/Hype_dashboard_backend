from __future__ import annotations

import threading
import time

from app.services.settings_service import get_settings_service


class CooldownService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[int, float] = {}

    def allow(self, employee_id: int) -> bool:
        cooldown = float(get_settings_service().get().cooldown_seconds)
        now = time.monotonic()
        with self._lock:
            last = self._last.get(employee_id)
            if last is not None and (now - last) < cooldown:
                return False
            self._last[employee_id] = now
            return True

    def reset(self, employee_id: int) -> None:
        with self._lock:
            self._last.pop(employee_id, None)

    def clear(self) -> None:
        with self._lock:
            self._last.clear()


_singleton: CooldownService | None = None
_singleton_lock = threading.Lock()


def get_cooldown_service() -> CooldownService:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = CooldownService()
    return _singleton

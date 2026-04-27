from __future__ import annotations

import os
import threading
import time
from typing import Any

import cv2
import numpy as np

from app.config import get_settings
from app.core.logger import get_logger

log = get_logger(__name__)

# Force RTSP control + media to flow over TCP. The default tries UDP for RTP,
# which fails on many networks (firewalls, NAT, missing routes back to the
# camera) and on TLS-required cameras (rtsps://). TCP is universally
# supported. Also enable a 5-second receive timeout so a broken stream gets
# cleaned up promptly. Set as a process-wide env var so OpenCV picks it up
# the first time `cv2.VideoCapture` is constructed; safe to set repeatedly.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000",
)


class RTSPReader:
    def __init__(self, url: str, name: str) -> None:
        self.url = url
        self.name = name
        self._cap: cv2.VideoCapture | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._backoff = 1.0
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _open(self) -> bool:
        settings = get_settings()
        try:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, settings.RTSP_CONNECT_TIMEOUT_MS)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, settings.RTSP_READ_TIMEOUT_MS)
            except Exception:
                pass
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            if not cap.isOpened():
                cap.release()
                return False
            with self._lock:
                self._cap = cap
            self._last_error = None
            self._backoff = 1.0
            log.info("[%s] RTSP opened", self.name)
            return True
        except Exception as exc:
            self._last_error = str(exc)
            log.warning("[%s] RTSP open failed: %s", self.name, exc)
            return False

    def _close(self) -> None:
        with self._lock:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

    def read(self) -> np.ndarray | None:
        if self._stop.is_set():
            return None
        with self._lock:
            cap = self._cap
        if cap is None:
            if not self._open():
                self._wait_backoff()
                return None
            with self._lock:
                cap = self._cap
            if cap is None:
                return None

        try:
            ok, frame = cap.read()
        except Exception as exc:
            self._last_error = str(exc)
            log.warning("[%s] RTSP read exception: %s", self.name, exc)
            self._close()
            self._wait_backoff()
            return None

        if not ok or frame is None:
            self._last_error = "empty frame"
            log.warning("[%s] RTSP read returned empty frame; reconnecting", self.name)
            self._close()
            self._wait_backoff()
            return None

        return frame

    def _wait_backoff(self) -> None:
        settings = get_settings()
        delay = min(self._backoff, float(settings.RTSP_RECONNECT_MAX_SECONDS))
        self._stop.wait(delay)
        self._backoff = min(self._backoff * 2, float(settings.RTSP_RECONNECT_MAX_SECONDS))

    def stop(self) -> None:
        self._stop.set()
        self._close()

    def __enter__(self) -> "RTSPReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

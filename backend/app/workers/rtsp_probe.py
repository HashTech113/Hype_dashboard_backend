from __future__ import annotations

import os
import time
from dataclasses import dataclass

import cv2

from app.core.logger import get_logger

log = get_logger(__name__)

# Match the camera worker: force RTSP over TCP. Required for many cameras
# (NAT/firewall blocked UDP, rtsps:// TLS-required models). Set once,
# inherited by every cv2.VideoCapture in this process.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000",
)


@dataclass
class ProbeOutcome:
    ok: bool
    width: int | None
    height: int | None
    elapsed_ms: int
    error: str | None


def probe_rtsp(url: str, *, timeout_ms: int = 5000) -> ProbeOutcome:
    """Try to open `url` and read one frame within `timeout_ms`.

    Short-lived — opens and closes a dedicated VideoCapture just for the test.
    Never raises; always returns a ProbeOutcome.
    """
    start = time.monotonic()
    cap: cv2.VideoCapture | None = None
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout_ms))
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(timeout_ms))
        except Exception:
            pass
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        if not cap.isOpened():
            elapsed = int((time.monotonic() - start) * 1000)
            return ProbeOutcome(False, None, None, elapsed, "could not open stream")

        ok, frame = cap.read()
        elapsed = int((time.monotonic() - start) * 1000)
        if not ok or frame is None:
            return ProbeOutcome(False, None, None, elapsed, "opened but no frame received")
        h, w = frame.shape[:2]
        return ProbeOutcome(True, int(w), int(h), elapsed, None)
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        log.warning("RTSP probe exception for %s: %s", url, exc)
        return ProbeOutcome(False, None, None, elapsed, str(exc))
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

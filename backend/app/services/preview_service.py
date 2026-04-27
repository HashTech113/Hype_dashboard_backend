"""Draws bounding-box overlays for the live camera preview.

Pure-function module — no DB, no model state, no I/O. Takes the latest
frame from a camera worker and the per-face detections from that same
tick, and produces an annotated JPEG byte stream suitable for the
`/cameras/{id}/preview.jpg` endpoint.

Color convention (BGR — OpenCV native):
  * Green   — face matched a known employee
  * Red     — face was unknown (no match above threshold)
  * White   — label text on top of a filled colored band
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Final

import cv2
import numpy as np

if TYPE_CHECKING:
    from app.workers.camera_worker import FrameDetection


_MATCHED_COLOR: Final[tuple[int, int, int]] = (0, 200, 0)  # BGR — green
_UNKNOWN_COLOR: Final[tuple[int, int, int]] = (0, 0, 220)  # BGR — red
_TEXT_COLOR: Final[tuple[int, int, int]] = (255, 255, 255)
_FONT: Final[int] = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE: Final[float] = 0.55
_FONT_THICKNESS: Final[int] = 1
_BOX_THICKNESS: Final[int] = 2
_LABEL_PAD_X: Final[int] = 6
_LABEL_PAD_Y: Final[int] = 5
_DEFAULT_JPEG_QUALITY: Final[int] = 80


def annotate_frame(
    frame: np.ndarray, detections: "list[FrameDetection]"
) -> np.ndarray:
    """Return a copy of `frame` with one labeled rectangle per detection."""
    if frame is None or frame.size == 0:
        return frame
    out = frame.copy()
    h, w = out.shape[:2]
    for det in detections:
        color = _MATCHED_COLOR if det.matched else _UNKNOWN_COLOR
        x1, y1, x2, y2 = det.bbox
        # Clamp bbox to frame bounds so cv2.rectangle never errors out.
        x1c = max(0, min(int(x1), w - 1))
        y1c = max(0, min(int(y1), h - 1))
        x2c = max(0, min(int(x2), w - 1))
        y2c = max(0, min(int(y2), h - 1))
        if x2c <= x1c or y2c <= y1c:
            continue
        cv2.rectangle(out, (x1c, y1c), (x2c, y2c), color, _BOX_THICKNESS)

        label = (
            f"{det.label} {int(round(det.score * 100))}%"
            if det.matched
            else "Unknown"
        )
        (text_w, text_h), baseline = cv2.getTextSize(
            label, _FONT, _FONT_SCALE, _FONT_THICKNESS
        )
        # Place the label band above the box; if the box is at the top
        # of the frame, place it inside the box instead so it's never
        # clipped.
        band_h = text_h + baseline + _LABEL_PAD_Y * 2
        if y1c - band_h < 0:
            band_y1 = y1c
            band_y2 = min(h - 1, y1c + band_h)
            text_y = band_y2 - _LABEL_PAD_Y - baseline
        else:
            band_y1 = max(0, y1c - band_h)
            band_y2 = y1c
            text_y = band_y2 - _LABEL_PAD_Y - baseline
        band_x1 = x1c
        band_x2 = min(w - 1, x1c + text_w + _LABEL_PAD_X * 2)
        cv2.rectangle(
            out, (band_x1, band_y1), (band_x2, band_y2), color, thickness=-1
        )
        cv2.putText(
            out,
            label,
            (band_x1 + _LABEL_PAD_X, text_y),
            _FONT,
            _FONT_SCALE,
            _TEXT_COLOR,
            _FONT_THICKNESS,
            cv2.LINE_AA,
        )
    return out


def encode_jpeg(frame: np.ndarray, *, quality: int = _DEFAULT_JPEG_QUALITY) -> bytes:
    """Encode a BGR frame to JPEG bytes."""
    ok, buf = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    )
    if not ok:
        raise RuntimeError("Failed to encode preview JPEG")
    return buf.tobytes()

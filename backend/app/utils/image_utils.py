from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def decode_image_bytes(data: bytes) -> np.ndarray | None:
    arr = np.frombuffer(data, dtype=np.uint8)
    if arr.size == 0:
        return None
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def write_jpeg(path: Path, image: np.ndarray, quality: int = 90) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError(f"Failed to encode JPEG for {path}")
    path.write_bytes(buf.tobytes())


def crop_bbox(image: np.ndarray, bbox: tuple[int, int, int, int], pad: float = 0.2) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    bw = x2 - x1
    bh = y2 - y1
    px = int(bw * pad)
    py = int(bh * pad)
    x1 = max(0, x1 - px)
    y1 = max(0, y1 - py)
    x2 = min(w, x2 + px)
    y2 = min(h, y2 + py)
    return image[y1:y2, x1:x2].copy()

"""Face quality assessment for the unknown-capture pipeline.

Pure-function module — no DB, no model state, no I/O. Operates on a single
detected face (BGR frame + bbox + 5-point landmarks + detector confidence)
and produces:

  * `FaceQualityMetrics` — every measurement we compute, regardless of
    pass/fail. Useful for telemetry and tuning.
  * `QualityVerdict` — a single accept/reject decision plus a short reason
    tag, gated against `QualityThresholds`.

Industry rationale per metric:

  * **Sharpness — Laplacian variance.** Pertuz/Puig/Garcia (2013) benchmarked
    36 focus measures; Laplacian variance is consistently in the top tier
    and is what OpenCV's blur-detection cookbook, dlib's enrollment guides,
    and on-device camera AF systems use. Higher = sharper.
  * **Brightness / contrast — HSV V channel.** The V (value) channel is
    closer to perceptual brightness than BT.601 luma for typical CCTV
    imagery (which often has muted color). We gate against an exposure
    window and a minimum standard deviation (contrast).
  * **Pose — 5-point landmark geometry.** buffalo_l returns the canonical
    five points (left_eye, right_eye, nose, left_mouth, right_mouth). For
    a frontal face the nose is equidistant from both eyes and the
    eye-line is horizontal. We measure:
      - `yaw_ratio`   = horizontal asymmetry of nose vs. eyes (0 frontal → 1 profile)
      - `pitch_ratio` = deviation of eye-nose-mouth vertical proportions
                        from the typical 1.3:1 frontal ratio
      - `eye_tilt_deg` = absolute angle of the eye line from horizontal

Thresholds split into runtime-tunable (admin settings) and module-fixed
(industry-standard constants that don't benefit from tuning).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np

# ----------------------------------------------------------------------
# Module-fixed constants (industry-standard; not exposed to admin)
# ----------------------------------------------------------------------

_LAPLACIAN_KERNEL: Final[int] = 3
_FACE_CROP_PAD_RATIO: Final[float] = 0.10
_FRONTAL_EYE_MOUTH_RATIO: Final[float] = 1.3


@dataclass(frozen=True)
class FaceQualityMetrics:
    """All quality measurements for a single detected face.

    Numeric metrics are always populated, even when the face is rejected,
    so callers can log borderline failures without recomputing.
    """

    width: int
    height: int
    smaller_side: int  # min(width, height) — gated against `min_face_size_px`
    det_score: float
    sharpness: float
    brightness: float
    contrast: float
    yaw_ratio: float
    pitch_ratio: float
    eye_tilt_deg: float


@dataclass(frozen=True)
class QualityThresholds:
    """Per-call thresholds. Caller pulls runtime-tunable values from
    `SettingsSnapshot` and may override module-fixed defaults if needed.
    """

    # Tunable via admin settings:
    min_face_size_px: int
    min_det_score: float
    min_sharpness: float

    # Fixed defaults — tuned for real CCTV. Strictness is on the
    # det_score / size / sharpness side (admin-tunable). Pose/lighting
    # are deliberately permissive: people walking past doorways are
    # rarely perfectly frontal, and dropping their captures gives the
    # admin nothing to label.
    min_brightness: float = 25.0
    max_brightness: float = 235.0
    min_contrast: float = 8.0
    max_yaw_ratio: float = 0.65       # was 0.35 — accept moderate profile
    max_pitch_ratio: float = 0.85     # was 0.55 — accept up/down tilt
    max_eye_tilt_deg: float = 45.0    # was 30.0


@dataclass(frozen=True)
class QualityVerdict:
    accepted: bool
    reason: str  # "ok" | "low_det_score" | "face_too_small" | "blurry" | ...
    metrics: FaceQualityMetrics


# ----------------------------------------------------------------------
# Low-level metric helpers (pure functions; safe on edge inputs)
# ----------------------------------------------------------------------


def _crop_face(
    frame_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
    pad_ratio: float = _FACE_CROP_PAD_RATIO,
) -> np.ndarray:
    """Crop the face region with a small pad, clamped to frame bounds."""
    if frame_bgr.size == 0:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    pad_x = int(bw * pad_ratio)
    pad_y = int(bh * pad_ratio)
    x1c = max(0, int(x1) - pad_x)
    y1c = max(0, int(y1) - pad_y)
    x2c = min(w, int(x2) + pad_x)
    y2c = min(h, int(y2) + pad_y)
    if x2c <= x1c or y2c <= y1c:
        return frame_bgr[0:0, 0:0]
    return frame_bgr[y1c:y2c, x1c:x2c]


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the Laplacian — the canonical blur metric.

    Higher value → sharper image. Empty inputs return 0 (treated as fully
    blurry by the gate).
    """
    if gray.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray, cv2.CV_64F, ksize=_LAPLACIAN_KERNEL).var())


def luminance_stats(face_bgr: np.ndarray) -> tuple[float, float]:
    """Mean and standard deviation of the HSV V channel — perceptual brightness
    and contrast within the face crop.
    """
    if face_bgr.size == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.float32)
    return float(v.mean()), float(v.std())


def estimate_yaw_ratio(kps: np.ndarray, face_width: int) -> float:
    """Yaw asymmetry on [0, 1]. 0 = perfectly frontal, 1 = full profile.

    Computed as |d_left_eye_to_nose - d_right_eye_to_nose| over their sum,
    using x-coordinates only. Scale-invariant (face_width arg accepted for
    future use; kept for API symmetry).
    """
    if kps is None or kps.shape[0] < 3:
        return 1.0
    if face_width <= 0:
        return 1.0
    le_x = float(kps[0, 0])
    re_x = float(kps[1, 0])
    nose_x = float(kps[2, 0])
    d_left = abs(nose_x - le_x)
    d_right = abs(re_x - nose_x)
    denom = d_left + d_right
    if denom < 1e-6:
        return 1.0
    return float(abs(d_left - d_right) / denom)


def estimate_pitch_ratio(kps: np.ndarray, face_height: int) -> float:
    """Pitch deviation from the typical frontal eye-nose-mouth proportion.

    Frontal adult faces sit near eye→nose : nose→mouth ≈ 1.3 : 1. Sharp
    up/down head tilts skew this proportion. Returns the magnitude of the
    relative deviation; 0 = exactly frontal.
    """
    if kps is None or kps.shape[0] < 5:
        return 1.0
    if face_height <= 0:
        return 1.0
    eyes_y = (float(kps[0, 1]) + float(kps[1, 1])) * 0.5
    nose_y = float(kps[2, 1])
    mouth_y = (float(kps[3, 1]) + float(kps[4, 1])) * 0.5
    eye_to_nose = max(1.0, nose_y - eyes_y)
    nose_to_mouth = max(1.0, mouth_y - nose_y)
    actual_ratio = eye_to_nose / nose_to_mouth
    return float(abs(actual_ratio - _FRONTAL_EYE_MOUTH_RATIO) / _FRONTAL_EYE_MOUTH_RATIO)


def estimate_eye_tilt_deg(kps: np.ndarray) -> float:
    """Absolute angle of the eye line from horizontal, in degrees [0, 90]."""
    if kps is None or kps.shape[0] < 2:
        return 0.0
    le = kps[0]
    re = kps[1]
    dx = float(re[0] - le[0])
    dy = float(re[1] - le[1])
    if abs(dx) < 1e-6:
        return 90.0
    angle = float(abs(np.degrees(np.arctan2(dy, dx))))
    if angle > 90.0:
        angle = 180.0 - angle
    return angle


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def measure(
    *,
    frame_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
    kps: np.ndarray,
    det_score: float,
) -> FaceQualityMetrics:
    """Compute every quality metric for one detected face.

    Pure function. Never raises on degenerate inputs — empty crops produce
    zero-valued metrics, which the gate will reject.
    """
    x1, y1, x2, y2 = bbox
    width = max(0, int(x2) - int(x1))
    height = max(0, int(y2) - int(y1))
    smaller = min(width, height)

    crop = _crop_face(frame_bgr, bbox)
    if crop.size > 0:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    sharpness = laplacian_variance(gray)
    brightness, contrast = luminance_stats(crop)
    yaw = estimate_yaw_ratio(kps, width)
    pitch = estimate_pitch_ratio(kps, height)
    tilt = estimate_eye_tilt_deg(kps)

    return FaceQualityMetrics(
        width=width,
        height=height,
        smaller_side=smaller,
        det_score=float(det_score),
        sharpness=sharpness,
        brightness=brightness,
        contrast=contrast,
        yaw_ratio=yaw,
        pitch_ratio=pitch,
        eye_tilt_deg=tilt,
    )


def evaluate(
    metrics: FaceQualityMetrics, thresholds: QualityThresholds
) -> QualityVerdict:
    """Apply gates in priority order; first failure wins.

    Order is chosen so that cheap signals (size, det_score) reject before
    we waste downstream effort on the same face crop.
    """
    if metrics.det_score < thresholds.min_det_score:
        return QualityVerdict(False, "low_det_score", metrics)
    if metrics.smaller_side < thresholds.min_face_size_px:
        return QualityVerdict(False, "face_too_small", metrics)
    if metrics.sharpness < thresholds.min_sharpness:
        return QualityVerdict(False, "blurry", metrics)
    if metrics.brightness < thresholds.min_brightness:
        return QualityVerdict(False, "underexposed", metrics)
    if metrics.brightness > thresholds.max_brightness:
        return QualityVerdict(False, "overexposed", metrics)
    if metrics.contrast < thresholds.min_contrast:
        return QualityVerdict(False, "low_contrast", metrics)
    if metrics.yaw_ratio > thresholds.max_yaw_ratio:
        return QualityVerdict(False, "non_frontal", metrics)
    if metrics.pitch_ratio > thresholds.max_pitch_ratio:
        return QualityVerdict(False, "extreme_pitch", metrics)
    if metrics.eye_tilt_deg > thresholds.max_eye_tilt_deg:
        return QualityVerdict(False, "tilted_head", metrics)
    return QualityVerdict(True, "ok", metrics)


def measure_and_evaluate(
    *,
    frame_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
    kps: np.ndarray,
    det_score: float,
    thresholds: QualityThresholds,
) -> QualityVerdict:
    """Convenience: measure + evaluate in one call. Most callers want this."""
    metrics = measure(
        frame_bgr=frame_bgr, bbox=bbox, kps=kps, det_score=det_score
    )
    return evaluate(metrics, thresholds)

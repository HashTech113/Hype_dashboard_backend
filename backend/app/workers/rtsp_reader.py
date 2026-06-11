"""Robust RTSP stream reader.

Design goals (from the bulletproof-RTSP audit):
  1. NEVER fail silently — every failure mode sets `last_error` with a
     human-readable string. The UI surfaces it directly.
  2. Distinguish transient failures (briefly unreachable, codec hiccup)
     from terminal ones (wrong URL, bad credentials, port closed for hours)
     and escalate to a DEGRADED state with slower retry cadence rather than
     spinning at 30s forever.
  3. Reset the backoff only after N consecutive *successful reads*, not on
     a bare open. A camera that opens then dies after 2 frames must not
     hammer reconnect at 1 s intervals.
  4. Expose every counter the operator might want — open_failures,
     read_failures, reconnects, health_state, last_error — so the API
     can show "82% of reads failed in the last minute" instead of a
     boolean.
"""
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

# FFmpeg options for low-latency RTSP. Each flag matters:
#   rtsp_transport=tcp   — UDP packets can drop & cause stutter; TCP is steady
#   stimeout=5000000     — 5s socket timeout (microseconds)
#   fflags=nobuffer      — don't pre-fill an input buffer
#   flags=low_delay      — short-circuit B-frame reordering (codec-level)
#   flush_packets=1      — flush packets immediately, no batching
#   reorder_queue_size=0 — disable RTP reorder buffer (0-10 frames otherwise)
#   max_delay=100000     — reduce internal A/V sync buffer to 100ms
#   probesize=32         — minimal probe (default 5MB!) so cap.read() returns immediately
#   analyzeduration=0    — don't pre-scan, start decoding the first frame at once
#
# Without these, FFmpeg holds 200-1000ms of frames "in case it needs to
# reorder B-frames" — which is the right call for VOD but completely wrong
# for live CCTV where freshness >> smoothness.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp"
    "|stimeout;5000000"
    "|fflags;nobuffer"
    "|flags;low_delay"
    "|flush_packets;1"
    "|reorder_queue_size;0"
    "|max_delay;100000"
    "|probesize;32"
    "|analyzeduration;0"
)


# After this many consecutive failures, switch from tight reconnect
# (1 → 2 → 4 → ... → 30 s) to slow-cadence DEGRADED mode where retries are
# spaced 60 s apart. Prevents log spam and CPU burn on permanently broken
# URLs. Operator sees the camera marked DEGRADED and knows action is needed.
_DEGRADED_AFTER_FAILURES: int = 10

# In DEGRADED mode, how long between retries. The system will pop out the
# moment a connection succeeds and resets the counter.
_DEGRADED_RETRY_SECONDS: float = 60.0

# Number of successful reads required to consider the stream "healthy" and
# fully reset the backoff. A flapping camera that delivers 3 frames then
# dies must NOT reset to 1s backoff after a single open.
_HEALTHY_READ_THRESHOLD: int = 30


class RTSPReader:
    def __init__(self, url: str, name: str) -> None:
        self.url = url
        self.name = name
        self._cap: cv2.VideoCapture | None = None
        self._stop = threading.Event()
        # RLock (not Lock) — read() holds the lock through cap.read() to
        # prevent a concurrent release() from segfaulting OpenCV/FFmpeg
        # (H1 fix). On a bad frame, read() calls _close() which would
        # otherwise deadlock with a plain Lock.
        self._lock = threading.RLock()

        # Backoff state
        self._backoff = 1.0
        self._last_error: str | None = None

        # Failure / success counters — exposed via properties for the API
        self._consecutive_open_failures = 0
        self._consecutive_read_failures = 0
        self._consecutive_good_reads = 0
        self._total_reconnects = 0
        self._total_open_failures = 0
        self._total_read_failures = 0
        self._first_open_at: float | None = None
        self._last_successful_read_at: float | None = None
        self._timeout_set_ok = True  # set False if cap.set timeout was rejected
        # Native FPS reported by the camera stream. Populated on first
        # successful open via cv2.CAP_PROP_FPS. Used by the camera worker
        # to drive its read loop at the camera's actual frame rate, instead
        # of an operator-supplied guess. Hikvision sub-stream typically
        # reports 15, main stream 25-30. Dahua sub 15. Reolink 20.
        self._detected_fps: float | None = None

        # ── CONTINUOUS-DRAIN THREAD ──────────────────────────────────────
        # The fundamental cause of multi-second RTSP lag is that FFmpeg
        # buffers H.264 frames as they arrive on the wire, and
        # `cap.read()` returns them IN ORDER. If the consumer pauses for
        # a fraction of a second (e.g. detection runs), the buffer fills
        # up — and consumers permanently see N-frames-old data because
        # each read() returns the OLDEST queued frame, not the latest.
        #
        # Fix: a dedicated background thread that does NOTHING but call
        # cap.read() in a tight loop, writing the latest frame to a
        # single-slot buffer. Consumers never touch FFmpeg directly —
        # they ask the reader for `latest_frame`, which returns whatever
        # the drain thread published microseconds ago. Result: every
        # consumer ALWAYS gets the most recent frame the camera sent.
        # End-to-end lag drops to ~one frame interval (50 ms at 20 fps).
        self._drain_thread: threading.Thread | None = None
        self._drain_stop = threading.Event()
        self._latest_drained: tuple[np.ndarray, float] | None = None
        # Condition on the drain output, sharing self._lock as its
        # underlying lock to prevent nested lock-ordering deadlocks
        # (previously _lock -> _drained_lock could circular-wait against
        # any path acquiring them in the reverse order). Consumers (live
        # preview WS, MJPEG stream, camera worker) wait on this to wake
        # up the INSTANT a new frame is published — no polling, no
        # fixed-rate pacing, no CPU spin. This is what eliminates the
        # last source of avoidable latency: previously the worker slept
        # on a `pace = 1/fps` timer between reads and so could be up to
        # one frame-interval behind the drain output. With this
        # Condition the worker wakes within microseconds of the camera
        # publishing.
        self._drained_condition = threading.Condition(self._lock)

    # ---- introspection properties -----------------------------------------

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def consecutive_open_failures(self) -> int:
        return self._consecutive_open_failures

    @property
    def consecutive_read_failures(self) -> int:
        return self._consecutive_read_failures

    @property
    def total_reconnects(self) -> int:
        return self._total_reconnects

    @property
    def last_successful_read_age_seconds(self) -> float | None:
        if self._last_successful_read_at is None:
            return None
        return max(0.0, time.monotonic() - self._last_successful_read_at)

    @property
    def detected_fps(self) -> float | None:
        return self._detected_fps

    @property
    def health_state(self) -> str:
        """One of: CONNECTING, STREAMING, FLAPPING, DEGRADED.

        - CONNECTING: never delivered a frame yet
        - STREAMING: currently delivering frames
        - FLAPPING: delivered frames recently but having intermittent issues
        - DEGRADED: too many consecutive failures — slow-cadence retry mode
        """
        if self._consecutive_open_failures >= _DEGRADED_AFTER_FAILURES:
            return "DEGRADED"
        if self._last_successful_read_at is None:
            return "CONNECTING"
        if self._consecutive_good_reads >= _HEALTHY_READ_THRESHOLD:
            return "STREAMING"
        return "FLAPPING"

    # ---- core connect / read logic ----------------------------------------

    def _open(self) -> bool:
        settings = get_settings()
        cap: cv2.VideoCapture | None = None
        try:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            try:
                ok1 = cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, settings.RTSP_CONNECT_TIMEOUT_MS)
                ok2 = cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, settings.RTSP_READ_TIMEOUT_MS)
                if not (ok1 and ok2) and self._timeout_set_ok:
                    self._timeout_set_ok = False
                    log.warning(
                        "[%s] cv2.set timeout was rejected — relying on FFmpeg "
                        "stimeout env var instead. Software watchdog may be needed.",
                        self.name,
                    )
            except Exception as exc:
                if self._timeout_set_ok:
                    self._timeout_set_ok = False
                    log.warning(
                        "[%s] cv2.set timeout raised: %s — relying on FFmpeg stimeout",
                        self.name,
                        exc,
                    )
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            opened = False
            try:
                opened = bool(cap.isOpened())
            except Exception as exc:
                # Very rare — but isOpened() has crashed on broken FFmpeg
                # builds before. Always treat as failure rather than leak.
                log.warning("[%s] cap.isOpened raised: %s", self.name, exc)
                opened = False
            if not opened:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None  # null so finally doesn't double-release
                self._record_open_failure(
                    "VideoCapture failed to open the stream — common causes: "
                    "wrong URL path, wrong credentials, unsupported codec, "
                    "or camera unreachable on this port."
                )
                return False
            # Hand off ownership to self._cap. Null `cap` so finally can't
            # accidentally release the live handle we're returning.
            # Auto-detect the native FPS before transferring ownership so the
            # worker can drive its read loop at the camera's real frame rate
            # instead of a hardcoded guess. cv2.CAP_PROP_FPS is read from
            # the SDP/RTSP description and reflects what the camera will send.
            try:
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                # Sanity bounds: occasional streams report 0 or absurd values.
                # Most CCTV streams are between 5 and 60 fps.
                if 1.0 <= fps <= 120.0:
                    self._detected_fps = fps
                    log.info("[%s] Native FPS detected: %.1f", self.name, fps)
                else:
                    log.info(
                        "[%s] cv2 reported FPS=%s (out of sane range) — "
                        "worker will use settings value",
                        self.name,
                        fps,
                    )
            except Exception as exc:
                log.debug("[%s] CAP_PROP_FPS read failed: %s", self.name, exc)

            with self._lock:
                self._cap = cap
            cap = None
            if self._first_open_at is None:
                self._first_open_at = time.monotonic()
            self._consecutive_open_failures = 0
            self._total_reconnects += 1
            self._last_error = None
            log.info("[%s] RTSP opened (reconnect #%d)", self.name, self._total_reconnects)
            # Kick off the continuous-drain thread so all subsequent
            # consumer reads come from the freshest-frame slot, never
            # blocking on FFmpeg.
            self._start_drain_thread()
            return True
        except Exception as exc:
            self._record_open_failure(str(exc) or repr(exc))
            log.warning("[%s] RTSP open exception: %s", self.name, exc)
            return False
        finally:
            # Belt-and-suspenders: if we exited the try by exception while
            # cap was still owned by us locally, release it. Set to None on
            # successful hand-off above so this is a no-op then.
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def _record_open_failure(self, reason: str) -> None:
        self._consecutive_open_failures += 1
        self._total_open_failures += 1
        # Compose error with failure count so the UI can show progress.
        self._last_error = (
            f"{reason} (open failure #{self._consecutive_open_failures})"
        )
        if self._consecutive_open_failures == _DEGRADED_AFTER_FAILURES:
            log.error(
                "[%s] %d consecutive open failures — entering DEGRADED mode "
                "(retry every %.0fs). Last reason: %s",
                self.name,
                _DEGRADED_AFTER_FAILURES,
                _DEGRADED_RETRY_SECONDS,
                reason,
            )

    def _close(self) -> None:
        # Stop the drain thread first so it doesn't race with the release.
        self._stop_drain_thread()
        with self._lock:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception as exc:
                    log.warning("[%s] cap.release raised: %s", self.name, exc)
                self._cap = None
            # Clear the latest-frame slot so a stale frame from the
            # previous connection isn't served after reconnect. Use the
            # Condition (same underlying lock) so we also wake any
            # blocked waiters — they'll see _latest_drained=None and
            # return None (timeout-like).
            with self._drained_condition:
                self._latest_drained = None
                self._drained_condition.notify_all()

    def _start_drain_thread(self) -> None:
        """Spin up the background drain loop after a successful _open()."""
        if self._drain_thread is not None and self._drain_thread.is_alive():
            return  # already running
        self._drain_stop.clear()
        t = threading.Thread(
            target=self._drain_loop,
            name=f"rtsp-drain[{self.name}]",
            daemon=True,
        )
        self._drain_thread = t
        t.start()

    def _stop_drain_thread(self) -> None:
        self._drain_stop.set()
        t = self._drain_thread
        # If we're being called FROM the drain thread itself (e.g. _close()
        # invoked via _read_blocking() during error recovery), we cannot
        # join ourselves — that would block for the full timeout and then
        # leave the thread reference in a weird state. Just signal stop and
        # let the drain loop notice _drain_stop on its next iteration.
        if t is not None and t is threading.current_thread():
            return
        if t is not None and t.is_alive():
            t.join(timeout=1.5)
            # If the drain thread is still alive, it's almost certainly
            # blocked inside cap.read() on a stuck RTSP connection. The
            # stop flag will never be checked until cap.read() returns,
            # which may be never. Forcefully release the VideoCapture
            # handle to unblock FFmpeg and let the thread exit. Without
            # this, the thread is orphaned, keeps holding the handle, and
            # leaks file descriptors / sockets on every reconnect.
            if t.is_alive():
                log.warning(
                    "[%s] drain thread did not stop within 1.5s — forcing "
                    "cap.release() to unblock cap.read()",
                    self.name,
                )
                stuck_cap = self._cap
                if stuck_cap is not None:
                    try:
                        stuck_cap.release()
                    except Exception as exc:
                        log.warning(
                            "[%s] forced cap.release raised: %s", self.name, exc
                        )
                    self._cap = None
                # Give the now-unblocked drain thread a brief moment to
                # notice _drain_stop and exit cleanly. If it still won't
                # die, abandon the reference rather than block shutdown.
                t.join(timeout=1.5)
                if t.is_alive():
                    log.error(
                        "[%s] drain thread still alive after forced release "
                        "— orphaning thread reference",
                        self.name,
                    )
        self._drain_thread = None

    def _drain_loop(self) -> None:
        """Tight loop that keeps FFmpeg's input queue empty.

        cap.read() blocks until the next frame arrives — so this thread
        naturally paces at the camera's native frame rate. Whatever the
        camera sends, we immediately publish to _latest_drained. The
        single-slot semantics mean a slow consumer never accumulates
        backlog — only the FRESHEST frame is ever visible.

        If FFmpeg has buffered N frames upstream (typical when a network
        hiccup briefly halts our read pace), the tight loop drains them
        all in milliseconds, then settles back to ~1 read per frame
        interval.

        Errors here mark the reader unhealthy but DON'T exit the thread —
        we keep retrying via the main read path's reconnect logic.
        """
        log.debug("[%s] drain thread started", self.name)
        while not self._drain_stop.is_set() and not self._stop.is_set():
            frame = self._read_blocking()
            if frame is None:
                # Either we're reconnecting (backoff sleeps inside _read_blocking)
                # or the camera died. Loop tries again either way; backoff
                # handles the timing.
                continue
            # Publish the freshest frame AND wake any blocked waiters.
            # Single-slot: any consumer reading _latest_drained gets THIS
            # frame next, not a stale predecessor. notify_all() wakes the
            # camera worker (for detection) and any WebSocket preview
            # streams within microseconds of the camera's H.264 frame
            # being decoded.
            with self._drained_condition:
                self._latest_drained = (frame, time.monotonic())
                self._drained_condition.notify_all()
        log.debug("[%s] drain thread stopped", self.name)

    def wait_next_drained_frame(
        self,
        last_ts: float,
        *,
        timeout: float = 1.0,
    ) -> tuple[np.ndarray, float] | None:
        """Block until the drain thread publishes a frame newer than
        `last_ts`, then return (frame_copy, timestamp).

        Returns None on timeout. Event-driven — no polling, no
        per-iteration sleeps. The wakeup happens INSIDE the drain
        thread's `notify_all()` call, so the producer→consumer
        latency is just the time the OS needs to schedule the
        waiting thread (~1 ms on a healthy box).

        Returns a `.copy()` of the frame so the caller can hold it
        across drain-thread updates without race risk.
        """
        with self._drained_condition:
            ok = self._drained_condition.wait_for(
                lambda: (
                    self._latest_drained is not None
                    and self._latest_drained[1] > last_ts
                ),
                timeout=timeout,
            )
            if not ok or self._latest_drained is None:
                return None
            frame, ts = self._latest_drained
            # Copy under the lock so the drain thread can't swap the
            # buffer mid-copy. After this returns the caller owns its
            # own ndarray.
            return frame.copy(), ts

    def read(self) -> np.ndarray | None:
        """Return the most-recently drained frame, or None if not ready.

        NON-BLOCKING. This is what the camera worker calls every tick. The
        drain thread (started by _open via _start_drain_thread) keeps a
        single-slot buffer of the latest frame FFmpeg has delivered. Worker
        consumers read that slot directly — they never wait on FFmpeg, so
        they never accumulate the buffer lag that was causing 5+ second
        delays.

        If the drain thread hasn't published a frame yet (cold start or
        reconnecting), we trigger an open by falling through to the
        blocking path once. After that, the drain thread takes over.
        """
        if self._stop.is_set():
            return None

        # Fast path: hand back whatever the drain thread published.
        with self._lock:
            latest = self._latest_drained
        if latest is not None:
            frame, ts = latest
            # Reject extremely old frames (camera died, drain stuck) so
            # the worker doesn't display week-old data. 2s is a generous
            # bound — FFmpeg reconnect typically completes faster.
            if time.monotonic() - ts < 2.0:
                return frame

        # Cold start — drain thread hasn't published anything yet. Trigger
        # an open via the blocking path; the drain thread will be started
        # inside _open() so future calls go through the fast path.
        return self._read_blocking()

    def _read_blocking(self) -> np.ndarray | None:
        """Original blocking read — used by the drain thread and as a
        one-shot cold-start path before the drain thread has any data.

        Calls cap.read() which blocks until FFmpeg has a frame. The drain
        thread runs this in a tight loop, always overwriting the single
        latest-frame slot."""
        if self._stop.is_set():
            return None
        bad_frame_reason: str | None = None
        bad_frame_exc: Exception | None = None
        with self._lock:
            cap = self._cap
            if cap is None:
                # Need to open. _open() acquires self._lock itself; RLock
                # allows re-entry from the same thread.
                if not self._open():
                    # Drop the lock before sleeping in _wait_backoff().
                    pass  # fall through to backoff below
                else:
                    cap = self._cap
                    if cap is None:
                        self._last_error = "open succeeded but capture handle was closed concurrently"
            if cap is None:
                # Fall through to backoff (outside the lock).
                pass
            else:
                try:
                    # The worker already runs cap.read() in a tight loop at the
                    # camera's native FPS, so each call returns the next frame
                    # ~50ms later. The freshness guarantee comes from FFmpeg's
                    # low-latency flags (nobuffer, low_delay, flush_packets,
                    # reorder_queue_size=0) set at process startup. We don't
                    # need to grab-drain here.
                    ok, frame = cap.read()
                except Exception as exc:
                    bad_frame_exc = exc
                    self._record_read_failure(f"cap.read raised: {exc}")
                else:
                    if not ok or frame is None:
                        bad_frame_reason = "empty frame"
                        self._record_read_failure(bad_frame_reason)
                    else:
                        # Successful read — track it under the lock, return outside.
                        self._consecutive_read_failures = 0
                        self._consecutive_good_reads += 1
                        self._last_successful_read_at = time.monotonic()
                        if self._consecutive_good_reads >= _HEALTHY_READ_THRESHOLD:
                            self._backoff = 1.0
                            self._last_error = None
                        return frame
                # Reaches here on bad frame OR exception: close under the
                # SAME lock (RLock re-entry) so we never leave a dead cap.
                if bad_frame_exc is not None or bad_frame_reason is not None:
                    self._close()

        # Outside the lock: log and back off. We deliberately moved sleeping
        # out of the critical section so stop() can interrupt promptly.
        if bad_frame_exc is not None:
            log.warning("[%s] RTSP read exception: %s", self.name, bad_frame_exc)
        elif bad_frame_reason is not None:
            log.warning("[%s] RTSP read returned empty frame; reconnecting", self.name)
        self._wait_backoff()
        return None

    def _record_read_failure(self, reason: str) -> None:
        self._consecutive_read_failures += 1
        self._consecutive_good_reads = 0
        self._total_read_failures += 1
        self._last_error = (
            f"{reason} (read failure #{self._consecutive_read_failures})"
        )

    def _wait_backoff(self) -> None:
        settings = get_settings()
        if self._consecutive_open_failures >= _DEGRADED_AFTER_FAILURES:
            # DEGRADED mode — slow retries to spare CPU + log noise after
            # ~10 consecutive failures the camera is probably gone for a
            # while (power-down, lunch break, weekend). Wait 60s.
            delay = _DEGRADED_RETRY_SECONDS
        else:
            # ACTIVE-RECONNECT mode — cap at 5s instead of the legacy
            # RTSP_RECONNECT_MAX_SECONDS (which defaults to 30s). When a
            # camera disconnects briefly (network blip, PoE port flap,
            # rebooting NVR), we want frames back within seconds, not
            # half a minute. 5s is short enough that the operator never
            # sees a "the camera's back, why isn't it showing" gap.
            cap = min(5.0, float(settings.RTSP_RECONNECT_MAX_SECONDS))
            delay = min(self._backoff, cap)
            self._backoff = min(self._backoff * 2, cap)
        # Use wait so a stop() request escapes immediately.
        self._stop.wait(delay)

    def stop(self) -> None:
        self._stop.set()
        self._close()

    def __enter__(self) -> "RTSPReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

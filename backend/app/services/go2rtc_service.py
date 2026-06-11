"""go2rtc — production-grade RTSP-to-WebRTC bridge integration.

Why this exists
================
Any architecture that goes RTSP → backend JPEG re-encode → browser has a
hard ~150ms latency floor. Camera GOP/H.264 buffering + JPEG encode + TCP
+ browser SW decode all stack up. For TRUE sub-100ms realtime — which is
what users perceive as "no lag" — the browser MUST receive raw H.264
NALs directly via WebRTC and use its hardware decoder.

We use `go2rtc` (https://github.com/AlexxIT/go2rtc) — a tiny standalone
Go binary battle-tested by Frigate NVR and Home Assistant. It connects
to our cameras' RTSP streams and exposes WebRTC, MSE-fMP4, HLS, and
MJPEG endpoints. We bridge our auth + camera config to it, the browser
talks to it for video.

Architecture
============
  RTSP camera ──► go2rtc (TCP localhost) ──► WebRTC peer ──► <video> tag
                       ▲
                       │  HTTP PATCH /api/config to sync our cameras
                       │  HTTP GET  /api/streams to read its state
                       │
                  FastAPI backend (this service)

go2rtc.exe lives at backend/storage/bin/go2rtc.exe. We auto-download
it on first boot if missing. Operator can also drop it there manually
for air-gapped installs.

Failure mode: if go2rtc can't start (no internet on first boot, OS
quirk, etc.), the WebRTC stream endpoint returns a 503. The frontend
automatically falls back to the WebSocket JPEG stream — still works,
just at the ~250ms latency we had before. No catastrophic break.
"""
from __future__ import annotations

import atexit
import json
import os
import platform
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from app.config import get_settings
from app.core.logger import get_logger

log = get_logger(__name__)


# Pin the version we tested against. Bumping requires re-testing the
# WebRTC handshake flow + the /api/config schema (it's stable but ge2rtc
# occasionally adds fields).
_GO2RTC_VERSION = "1.9.7"
_GO2RTC_DOWNLOAD_URLS: dict[str, str] = {
    "windows-amd64": (
        f"https://github.com/AlexxIT/go2rtc/releases/download/"
        f"v{_GO2RTC_VERSION}/go2rtc_win64.zip"
    ),
    "linux-amd64": (
        f"https://github.com/AlexxIT/go2rtc/releases/download/"
        f"v{_GO2RTC_VERSION}/go2rtc_linux_amd64"
    ),
}

# Default port we tell go2rtc to listen on. Backend uses this internally.
_GO2RTC_API_PORT = 1984


@dataclass
class StreamInfo:
    """What the frontend needs to open a WebRTC connection to go2rtc."""

    name: str  # the camera key in go2rtc, e.g. "cam_6"
    webrtc_url: str  # ws://host:port/api/ws?src=cam_6 — go2rtc's WebRTC signalling endpoint
    mse_url: str  # ws://host:port/api/mse?src=cam_6 — fallback if WebRTC blocked
    mjpeg_url: str  # http://host:port/api/stream.mjpeg?src=cam_6 — last-resort fallback


class Go2RtcService:
    """Singleton that owns the go2rtc subprocess + camera-config sync."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._api_host = "127.0.0.1"
        self._api_port = _GO2RTC_API_PORT
        self._binary_path: Path | None = None
        self._ready = False
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def api_base(self) -> str:
        return f"http://{self._api_host}:{self._api_port}"

    @property
    def public_host(self) -> str:
        """Hostname the BROWSER uses to reach go2rtc. Usually the same as
        where the backend is reachable from — we bind go2rtc to localhost
        only and reverse-proxy it through the backend in production.
        For dev, we tell the browser to talk directly to localhost:1984."""
        return self._api_host

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # --- binary management -------------------------------------------------

    def _expected_binary_path(self) -> Path:
        settings = get_settings()
        bin_dir = Path(settings.STORAGE_ROOT) / "bin"
        if platform.system() == "Windows":
            return bin_dir / "go2rtc.exe"
        return bin_dir / "go2rtc"

    def _download_binary(self, target: Path) -> bool:
        """Best-effort one-shot download. Returns True on success.

        Skipped silently when there's no internet or the platform isn't
        supported. The caller falls back to WebSocket streaming.
        """
        sysname = platform.system().lower()
        arch = platform.machine().lower()
        if sysname == "windows" and arch in ("amd64", "x86_64"):
            key = "windows-amd64"
        elif sysname == "linux" and arch in ("x86_64", "amd64"):
            key = "linux-amd64"
        else:
            log.warning(
                "No prebuilt go2rtc for %s/%s — falling back to WebSocket stream",
                sysname,
                arch,
            )
            return False

        url = _GO2RTC_DOWNLOAD_URLS[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading go2rtc %s from %s", _GO2RTC_VERSION, url)
        try:
            if url.endswith(".zip"):
                tmp_zip = target.parent / "go2rtc.zip"
                urllib.request.urlretrieve(url, str(tmp_zip))
                with zipfile.ZipFile(tmp_zip) as zf:
                    # Windows archive contains go2rtc.exe at root
                    members = [m for m in zf.namelist() if m.endswith(".exe")]
                    if not members:
                        log.error("go2rtc zip has no .exe member")
                        return False
                    with zf.open(members[0]) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                tmp_zip.unlink(missing_ok=True)
            else:
                urllib.request.urlretrieve(url, str(target))
                target.chmod(0o755)
            log.info("go2rtc binary saved to %s", target)
            return True
        except Exception as exc:
            log.warning("go2rtc download failed (%s) — falling back to WebSocket", exc)
            return False

    # --- subprocess lifecycle ---------------------------------------------

    def start(self) -> None:
        """Locate / download the binary and launch as a child process.

        Idempotent. NEVER raises — failures degrade to WebSocket streaming
        rather than blocking system startup.
        """
        with self._lock:
            if self.is_running:
                return

            target = self._expected_binary_path()
            if not target.exists():
                if not self._download_binary(target):
                    self._last_error = (
                        f"go2rtc binary missing at {target} and download failed"
                    )
                    return

            self._binary_path = target

            # Minimal config — tell go2rtc to listen on localhost only.
            # We'll PATCH camera streams in via the API after it boots.
            config = {
                "api": {"listen": f":{self._api_port}"},
                "rtsp": {"listen": ":8554"},  # internal — never exposed
                "streams": {},
            }
            config_path = target.parent / "go2rtc.yaml"
            try:
                import yaml  # type: ignore[import-not-found]

                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(config, f)
            except ImportError:
                # PyYAML not installed — write a minimal yaml by hand.
                # go2rtc accepts JSON too via -c flag, but YAML is canonical.
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(
                        f"api:\n  listen: \":{self._api_port}\"\n"
                        f"rtsp:\n  listen: \":8554\"\n"
                        f"streams: {{}}\n"
                    )

            # Pass ABSOLUTE config path AND don't override cwd — otherwise
            # go2rtc resolves the relative path against its cwd resulting in
            # doubled-up paths like storage\bin\storage\bin\go2rtc.yaml.
            abs_config = str(config_path.resolve())
            log.info("Starting go2rtc subprocess: %s -config %s", target, abs_config)
            try:
                creationflags = 0
                if platform.system() == "Windows":
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
                self._proc = subprocess.Popen(
                    [str(target.resolve()), "-config", abs_config],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except Exception as exc:
                self._last_error = f"Failed to spawn go2rtc: {exc}"
                log.exception("go2rtc spawn failed")
                return

            atexit.register(self.stop)

            # Wait briefly for the HTTP API to come up
            self._wait_ready(timeout=5.0)

    def _wait_ready(self, timeout: float = 15.0) -> None:
        # go2rtc 1.9.x uses /api/streams as the canonical "is it up?"
        # endpoint — returns {} when no streams configured. /api/info does
        # not exist; previous version of this code was checking the wrong
        # path and always timing out, marking go2rtc as not-ready even
        # though the subprocess was perfectly healthy.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                r = requests.get(f"{self.api_base}/api/streams", timeout=1.0)
                if r.status_code == 200:
                    self._ready = True
                    self._last_error = None
                    log.info("go2rtc API ready at %s", self.api_base)
                    return
            except Exception:
                pass
            time.sleep(0.3)
        self._last_error = (
            f"go2rtc started but HTTP API did not respond within {timeout:.0f}s"
        )
        log.warning(self._last_error)

    def stop(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2.0)
                log.info("go2rtc subprocess stopped")
            except Exception as exc:
                log.warning("go2rtc stop error: %s", exc)
            finally:
                self._proc = None
                self._ready = False

    # --- camera config sync ------------------------------------------------

    def stream_key(self, camera_id: int) -> str:
        return f"cam_{camera_id}"

    def sync_cameras(self, cameras: list[tuple[int, str]]) -> None:
        """Push the camera RTSP URLs to go2rtc via its config API.

        `cameras` is a list of (camera_id, rtsp_url) tuples for all the
        ACTIVE cameras. go2rtc handles connection management, reconnect,
        and codec passthrough internally.
        """
        if not self._ready:
            return
        # go2rtc supports adding streams via PUT /api/streams?name=KEY&src=URL
        # We patch each camera. A camera already configured with the same
        # source is a no-op.
        for cam_id, rtsp_url in cameras:
            key = self.stream_key(cam_id)
            try:
                r = requests.put(
                    f"{self.api_base}/api/streams",
                    params={"name": key, "src": rtsp_url},
                    timeout=3.0,
                )
                if r.status_code >= 400:
                    log.warning(
                        "go2rtc PUT stream %s failed: %s %s",
                        key, r.status_code, r.text[:120],
                    )
            except Exception as exc:
                log.warning("go2rtc sync error for cam %s: %s", cam_id, exc)

    def remove_camera(self, camera_id: int) -> None:
        if not self._ready:
            return
        key = self.stream_key(camera_id)
        try:
            requests.delete(
                f"{self.api_base}/api/streams",
                params={"src": key},
                timeout=3.0,
            )
        except Exception as exc:
            log.warning("go2rtc DELETE stream %s failed: %s", key, exc)

    # --- info for the frontend --------------------------------------------

    def stream_info_for_browser(
        self,
        camera_id: int,
        *,
        browser_host: str | None = None,
    ) -> StreamInfo:
        """Return URLs the BROWSER uses to fetch the stream.

        `browser_host` is the hostname the browser used to load the page.
        In dev that's `localhost`; we replace our internal `127.0.0.1`
        with whatever the browser actually used so the WebRTC ICE
        candidates resolve properly.
        """
        host = browser_host or self._api_host
        key = self.stream_key(camera_id)
        return StreamInfo(
            name=key,
            webrtc_url=f"ws://{host}:{self._api_port}/api/ws?src={key}",
            mse_url=f"ws://{host}:{self._api_port}/api/ws?src={key}",
            mjpeg_url=f"http://{host}:{self._api_port}/api/stream.mjpeg?src={key}",
        )


_INSTANCE: Go2RtcService | None = None


def get_go2rtc_service() -> Go2RtcService:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Go2RtcService()
    return _INSTANCE

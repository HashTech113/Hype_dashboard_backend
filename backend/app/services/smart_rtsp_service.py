"""Bulletproof RTSP camera connector.

Given EITHER a user-supplied RTSP URL OR a (host, username, password)
tuple, walk a multi-step ladder to discover a working stream URL:

    1. URL hygiene       — strip whitespace, percent-encode reserved chars
                           that snuck into the userinfo segment (the classic
                           "raw @ in password" bug).
    2. TCP preflight     — open a TCP socket to host:port to prove the camera
                           is on-network. Without this, OpenCV's failure
                           message gives no signal whether the URL is wrong
                           vs the network is wrong.
    3. TLS detection     — send a plaintext OPTIONS over the socket, read 7
                           bytes, classify by first byte (R = plain RTSP,
                           0x15 = TLS-required Alert). Cameras like CP Plus
                           AT-series and modern Hikvision require RTSPS.
    4. ONVIF discovery   — if user gave credentials, call
                           GetSystemDateAndTime → GetProfiles → GetStreamUri
                           on standard ONVIF ports. This is THE most reliable
                           strategy because the camera tells us its own URL.
    5. Vendor fallbacks  — when ONVIF is off or the URL didn't help,
                           sequentially try a curated list of brand-specific
                           RTSP paths (Hikvision, Dahua/CP Plus, Axis,
                           Reolink/TP-Link, Foscam, Vivotek, Bosch,
                           generics).
    6. RTSP DESCRIBE     — for each candidate URL, send a real DESCRIBE over
                           a fresh socket. 200 OK means valid; 401 means
                           valid-but-wrong-creds (we know the PATH is right);
                           404 means try the next candidate. Fast — no full
                           pipeline open per attempt.
    7. OpenCV final test — once we have a strongly-indicated URL, do one
                           end-to-end open + first-frame read to confirm
                           OpenCV / FFmpeg can actually decode it.

Returns a structured result with one row per step so the UI can show
exactly which step succeeded / failed and what to try next.

This module never raises for connection failures — it always returns a
SmartProbeResult. It DOES raise for programmer errors (e.g. malformed
request) — those are the caller's responsibility.
"""
from __future__ import annotations

import re
import socket
import ssl
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import quote, urlsplit, urlunsplit

from app.core.logger import get_logger
from app.workers.rtsp_probe import probe_rtsp

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types — kept as plain dataclasses so they're cheap to construct and
# trivial to convert into pydantic SmartProbeStep / SmartProbeResult models.
# ---------------------------------------------------------------------------


@dataclass
class Step:
    name: str
    ok: bool
    duration_ms: int
    detail: str
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "detail": self.detail,
            "error": self.error,
        }


@dataclass
class ProbeResult:
    ok: bool
    strategy: str
    summary: str
    working_url: str | None = None
    width: int | None = None
    height: int | None = None
    vendor_hint: str | None = None
    suggestion: str | None = None
    steps: list[Step] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "strategy": self.strategy,
            "summary": self.summary,
            "working_url": self.working_url,
            "width": self.width,
            "height": self.height,
            "vendor_hint": self.vendor_hint,
            "suggestion": self.suggestion,
            "steps": [s.as_dict() for s in self.steps],
        }


@dataclass
class SmartProbeRequest:
    """Inputs to SmartRTSPService.probe — populated from the API schema."""

    host: str | None = None
    port: int = 554
    username: str | None = None
    password: str | None = None
    rtsp_url: str | None = None
    prefer_sub_stream: bool = True
    probe_timeout_seconds: int = 15


# ---------------------------------------------------------------------------
# Brand path tables — sourced from the research findings + production CCTV
# fleet experience. Order matters: most-common paths first per vendor.
# Each entry has {ip}, {user}, {pass}, {ch} as placeholders.
# ---------------------------------------------------------------------------

_BRAND_PATHS: dict[str, list[str]] = {
    "hikvision": [
        "rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{ch}01",
        "rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{ch}02",
        "rtsp://{user}:{pwd}@{ip}:{port}/h264/ch{ch}/main/av_stream",
        "rtsp://{user}:{pwd}@{ip}:{port}/h264/ch{ch}/sub/av_stream",
    ],
    "dahua": [  # also CP Plus, Amcrest, Honeywell (OEM Dahua)
        "rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=0",
        "rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1",
        "rtsp://{user}:{pwd}@{ip}:{port}/live",
    ],
    "cp_plus_at": [  # Newer CP Plus with ONVIF-style endpoint
        "rtsp://{user}:{pwd}@{ip}:{port}/video/live?channel={ch}&subtype=0&unicast=true&proto=Onvif",
        "rtsp://{user}:{pwd}@{ip}:{port}/video/live?channel={ch}&subtype=1&unicast=true&proto=Onvif",
    ],
    "axis": [
        "rtsp://{user}:{pwd}@{ip}:{port}/axis-media/media.amp?videocodec=h264",
        "rtsp://{user}:{pwd}@{ip}:{port}/axis-media/media.amp",
    ],
    "reolink_tplink": [
        "rtsp://{user}:{pwd}@{ip}:{port}/h264Preview_0{ch}_main",
        "rtsp://{user}:{pwd}@{ip}:{port}/h264Preview_0{ch}_sub",
        "rtsp://{user}:{pwd}@{ip}:{port}/stream1",
        "rtsp://{user}:{pwd}@{ip}:{port}/stream2",
    ],
    "foscam": [
        "rtsp://{user}:{pwd}@{ip}:{port}/videoMain",
        "rtsp://{user}:{pwd}@{ip}:{port}/videoSub",
    ],
    "vivotek": [
        "rtsp://{user}:{pwd}@{ip}:{port}/live.sdp",
        "rtsp://{user}:{pwd}@{ip}:{port}/live2.sdp",
    ],
    "bosch": [
        "rtsp://{user}:{pwd}@{ip}:{port}/?inst={ch}",
    ],
    "generic": [
        "rtsp://{user}:{pwd}@{ip}:{port}/live",
        "rtsp://{user}:{pwd}@{ip}:{port}/0",
        "rtsp://{user}:{pwd}@{ip}:{port}/1",
        "rtsp://{user}:{pwd}@{ip}:{port}/stream",
        "rtsp://{user}:{pwd}@{ip}:{port}/video1",
    ],
}

# Manufacturer name (from ONVIF GetDeviceInformation, lowercase) → vendor key
# in _BRAND_PATHS. Used to prioritize candidate paths.
_VENDOR_LOOKUP = {
    "hikvision": "hikvision",
    "dahua": "dahua",
    "amcrest": "dahua",
    "cp plus": "cp_plus_at",
    "cpplus": "cp_plus_at",
    "axis": "axis",
    "reolink": "reolink_tplink",
    "tp-link": "reolink_tplink",
    "tplink": "reolink_tplink",
    "foscam": "foscam",
    "vivotek": "vivotek",
    "bosch": "bosch",
    "honeywell": "dahua",
}


# ---------------------------------------------------------------------------
# Helpers — low-level probes used by SmartRTSPService.probe
# ---------------------------------------------------------------------------


def _build_url(template: str, *, ip: str, port: int, user: str, pwd: str, ch: int = 1) -> str:
    return template.format(ip=ip, port=port, user=quote(user, safe=""), pwd=quote(pwd, safe=""), ch=ch)


def _redact(url: str) -> str:
    """Redact credentials for logs / UI."""
    try:
        parts = urlsplit(url)
        if parts.username or parts.password:
            netloc = f"***:***@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            return urlunsplit(
                (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
            )
    except Exception:
        pass
    return url


def _tcp_probe(host: str, port: int, *, timeout: float = 3.0) -> Step:
    """Open a TCP socket. Distinguishes 'host unreachable' from 'wrong URL'."""
    t0 = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return Step(
            name="tcp_connect",
            ok=True,
            duration_ms=int((time.monotonic() - t0) * 1000),
            detail=f"TCP connected to {host}:{port}",
        )
    except socket.timeout:
        # The most COMMON failure cause is the operator typing a non-RTSP
        # port (80 = web UI, 8000/8080 = Hikvision SDK, 8554 = secondary
        # RTSP). Tell them that BEFORE the generic "is the cable plugged
        # in" advice — wrong-port is a 5-second fix, cable is a 5-minute
        # one.
        if port == 80:
            err = (
                "Port 80 is the camera's WEB UI, not its RTSP video stream. "
                "Try port 554 (standard RTSP) instead. If you don't know "
                "the camera's IP, close this and click 'Detect on LAN'."
            )
        elif port in (8000, 8080, 8899):
            err = (
                f"Port {port} is usually the camera's SDK / management "
                f"interface, not the RTSP video stream. Try port 554 first. "
                f"If you don't know the camera's IP, close this and click "
                f"'Detect on LAN'."
            )
        elif port not in (554, 322, 8554, 10554):
            err = (
                f"Port {port} is not a standard RTSP port. RTSP usually "
                f"runs on 554 (plaintext) or 322 (TLS). Try one of those."
            )
        else:
            err = (
                f"Camera did not respond on port {port}. Check: (1) the IP is "
                f"correct (use 'Detect on LAN' to find it), (2) the camera is "
                f"powered + connected to the same network as this PC, (3) "
                f"Windows Firewall isn't blocking outbound traffic."
            )
        return Step(
            name="tcp_connect",
            ok=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
            detail=f"TCP timeout connecting to {host}:{port}",
            error=err,
        )
    except OSError as exc:
        # 10061 = connection refused on Windows; 111 = ECONNREFUSED on Linux
        msg = str(exc)
        if "10061" in msg or "refused" in msg.lower():
            err = (
                f"Camera is on the network but port {port} is closed. "
                f"Try 8554, 10554, or 322 (TLS-RTSP)."
            )
        elif "10065" in msg or "unreachable" in msg.lower():
            err = "Camera is unreachable — check your network adapter is plugged in."
        elif "10060" in msg or "10013" in msg:
            err = "Connection blocked — check Windows Firewall and antivirus."
        else:
            err = msg
        return Step(
            name="tcp_connect",
            ok=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
            detail=f"TCP error on {host}:{port}",
            error=err,
        )


def _tls_detect(host: str, port: int, *, timeout: float = 5.0) -> Step:
    """Send plaintext OPTIONS, classify the first byte to detect TLS-required."""
    t0 = time.monotonic()
    probe_url = f"rtsp://{host}:{port}/"
    options = (
        f"OPTIONS {probe_url} RTSP/1.0\r\n"
        f"CSeq: 1\r\n"
        f"User-Agent: AI-Attendance-Probe/1.0\r\n"
        f"\r\n"
    ).encode("ascii")
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            sock.sendall(options)
            data = sock.recv(7)
        finally:
            sock.close()
    except (socket.timeout, OSError) as exc:
        # Connection reset is common for TLS-only cameras — retry as TLS.
        msg = str(exc).lower()
        if "reset" in msg or "10054" in msg:
            return Step(
                name="tls_detect",
                ok=True,
                duration_ms=int((time.monotonic() - t0) * 1000),
                detail="Camera reset plain RTSP — likely requires RTSPS (TLS).",
            )
        return Step(
            name="tls_detect",
            ok=False,
            duration_ms=int((time.monotonic() - t0) * 1000),
            detail=f"Could not probe {host}:{port}",
            error=str(exc),
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    if not data:
        # EOF with no bytes — also a TLS-required signature
        return Step(
            name="tls_detect",
            ok=True,
            duration_ms=elapsed,
            detail="Plain RTSP yielded EOF — camera likely requires RTSPS.",
        )
    first = data[0]
    if first == 0x52:  # 'R' — "RTSP/1.0 ..."
        return Step(
            name="tls_detect",
            ok=True,
            duration_ms=elapsed,
            detail="Plain RTSP accepted (no TLS required).",
        )
    if first == 0x15:  # TLS Alert
        return Step(
            name="tls_detect",
            ok=True,
            duration_ms=elapsed,
            detail="Camera replied with TLS Alert — requires RTSPS.",
        )
    if first == 0x16:  # TLS Handshake
        return Step(
            name="tls_detect",
            ok=True,
            duration_ms=elapsed,
            detail="Camera initiated TLS handshake — requires RTSPS.",
        )
    return Step(
        name="tls_detect",
        ok=False,
        duration_ms=elapsed,
        detail=f"Unrecognized response first byte: 0x{first:02X}",
        error="Unexpected response from camera.",
    )


def _rtsp_describe(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    """Send a real RTSP DESCRIBE, return (status_code, body).

    Returns (200, sdp), (401, body) — both indicate the path is correct,
    just one needs auth. (404, body) means the path is wrong.
    Returns (0, error_text) on transport failure.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or (554 if parts.scheme == "rtsp" else 322)
        is_tls = parts.scheme == "rtsps"
    except Exception as exc:
        return 0, f"URL parse: {exc}"
    if not host:
        return 0, "URL has no host"

    request = (
        f"DESCRIBE {url} RTSP/1.0\r\n"
        f"CSeq: 2\r\n"
        f"Accept: application/sdp\r\n"
        f"User-Agent: AI-Attendance-Probe/1.0\r\n"
        f"\r\n"
    ).encode("ascii", errors="ignore")

    raw: socket.socket | None = None
    sock: socket.socket | None = None
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
        if is_tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            except AttributeError:
                pass
            ctx.options |= ssl.OP_NO_TICKET
            try:
                ctx.set_ciphers(
                    "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:"
                    "AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:"
                    "AES128-SHA:AES256-SHA"
                )
            except ssl.SSLError:
                pass
            # wrap_socket may raise — catch in outer except so the raw socket
            # is still closed in `finally`. After successful wrap, sock owns
            # raw and closing sock closes both; we null `raw` to avoid double-close.
            sock = ctx.wrap_socket(raw, server_hostname=host)
            raw = None
        else:
            sock = raw
            raw = None
        sock.settimeout(timeout)
        sock.sendall(request)
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                buf = sock.recv(4096)
            except socket.timeout:
                break
            if not buf:
                break
            chunks.append(buf)
            if b"\r\n\r\n" in b"".join(chunks):
                # Headers complete — for DESCRIBE, headers are enough
                # to determine status; SDP body parsing not required.
                break

        body = b"".join(chunks).decode("ascii", errors="replace")
        m = re.match(r"RTSP/\d\.\d\s+(\d+)\s+", body)
        if m:
            return int(m.group(1)), body
        return 0, f"Non-RTSP response: {body[:80]!r}"
    except (socket.timeout, OSError, ssl.SSLError) as exc:
        return 0, str(exc)
    finally:
        # Close whichever sockets remain open. After a successful wrap,
        # raw is None and sock owns the underlying fd. On exception during
        # wrap, sock is None and raw must be closed.
        for s in (sock, raw):
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# ONVIF discovery — soft-imported so the system runs even without onvif-zeep
# ---------------------------------------------------------------------------


def _onvif_discover(host: str, username: str, password: str, *, timeout: float = 6.0) -> dict:
    """Use ONVIF to ask the camera for its own stream URL.

    Returns a dict with keys:
      - 'ok': bool
      - 'manufacturer': str | None
      - 'model': str | None
      - 'profiles': list[dict] with {'token','name','uri','width','height'}
      - 'error': str | None

    Each port is probed cheaply at the TCP layer first (fast fail), so the
    expensive SOAP roundtrips only happen on ports that respond. Total wall
    time is bounded by `timeout` rather than (ports × library default).
    """
    try:
        from onvif import ONVIFCamera  # type: ignore
    except ImportError:
        return {
            "ok": False,
            "manufacturer": None,
            "model": None,
            "profiles": [],
            "error": "onvif-zeep is not installed",
        }

    deadline = time.monotonic() + max(2.0, timeout)
    # Try the most common ONVIF ports in order. TCP-probe first; skip the
    # SOAP attempt if the port is closed.
    for onvif_port in (80, 8000, 8080, 8899, 2020, 10080):
        if time.monotonic() >= deadline:
            return {
                "ok": False,
                "manufacturer": None,
                "model": None,
                "profiles": [],
                "error": "ONVIF probe timeout",
            }
        # Cheap TCP probe — 1s timeout per port; if it's closed we skip
        # entirely instead of letting onvif-zeep wait its default ~30s.
        try:
            s = socket.create_connection((host, onvif_port), timeout=1.0)
            s.close()
        except (socket.timeout, OSError):
            continue
        try:
            cam = ONVIFCamera(host, onvif_port, username, password)
            # Some onvif-zeep constructors lazy-fetch services; force one call.
            info = cam.devicemgmt.GetDeviceInformation()
            manufacturer = getattr(info, "Manufacturer", None)
            model = getattr(info, "Model", None)

            media = cam.create_media_service()
            profiles_raw = media.GetProfiles()
            profile_list = []
            for p in profiles_raw:
                req = media.create_type("GetStreamUri")
                req.ProfileToken = p.token
                # newer onvif-zeep expects StreamSetup as a dict:
                req.StreamSetup = {
                    "Stream": "RTP-Unicast",
                    "Transport": {"Protocol": "RTSP"},
                }
                try:
                    uri_resp = media.GetStreamUri(req)
                    uri = getattr(uri_resp, "Uri", None) or str(uri_resp)
                except Exception as exc:
                    log.debug("GetStreamUri failed for %s: %s", p.token, exc)
                    uri = None
                if uri is None:
                    continue
                w = h = None
                try:
                    venc = p.VideoEncoderConfiguration
                    if venc and venc.Resolution:
                        w, h = int(venc.Resolution.Width), int(venc.Resolution.Height)
                except Exception:
                    pass
                profile_list.append(
                    {
                        "token": p.token,
                        "name": getattr(p, "Name", "") or "",
                        "uri": uri,
                        "width": w,
                        "height": h,
                    }
                )
            if profile_list:
                return {
                    "ok": True,
                    "manufacturer": manufacturer,
                    "model": model,
                    "profiles": profile_list,
                    "error": None,
                }
        except Exception as exc:
            log.debug("ONVIF on %s:%s failed: %s", host, onvif_port, exc)
            continue
    return {
        "ok": False,
        "manufacturer": None,
        "model": None,
        "profiles": [],
        "error": "ONVIF unreachable on standard ports (80, 8000, 8080, 8899, 2020, 10080)",
    }


def _inject_credentials(url: str, user: str, pwd: str) -> str:
    """Add credentials to a URL that ONVIF returned without them."""
    parts = urlsplit(url)
    if parts.username or parts.password:
        return url  # already has creds
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    new_netloc = f"{quote(user, safe='')}:{quote(pwd, safe='')}@{host}{port}"
    return urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, parts.fragment))


def _pick_profile(profiles: list[dict], prefer_sub: bool) -> dict:
    """Sort by pixel count, return main or sub depending on preference."""
    def pixels(p: dict) -> int:
        return (p.get("width") or 0) * (p.get("height") or 0)
    sorted_p = sorted(profiles, key=pixels, reverse=True)
    if prefer_sub and len(sorted_p) > 1:
        return sorted_p[-1]
    return sorted_p[0]


def _candidate_paths_for_vendor(
    vendor_key: str | None,
    *,
    prefer_sub: bool = True,
) -> list[str]:
    """Return brand-priority-ordered URL templates to try.

    When `prefer_sub=True` (default) the LOW-RES sub-stream path is tried
    BEFORE the main stream within each vendor block. Sub-stream typically
    runs at 480p-720p H.264 which decodes faster and drops latency
    dramatically vs the 4K main stream. The trade-off (lower face
    resolution at distance) is the right call for live monitoring.
    """
    order: list[str] = []
    if vendor_key and vendor_key in _BRAND_PATHS:
        order.append(vendor_key)
    for k in ("cp_plus_at", "dahua", "hikvision", "reolink_tplink", "axis", "foscam", "vivotek", "bosch", "generic"):
        if k not in order:
            order.append(k)
    out: list[str] = []
    for k in order:
        paths = list(_BRAND_PATHS[k])
        if prefer_sub:
            # Sort so paths containing sub-stream markers float to the top.
            # Markers used in our templates: "subtype=1", "/Channels/{ch}02",
            # "ch{ch}/sub", "Sub", "videoSub", "stream2", "live2".
            def is_sub(path: str) -> bool:
                p = path.lower()
                return any(
                    needle in p for needle in (
                        "subtype=1",
                        "/channels/{ch}02",
                        "ch{ch}/sub",
                        "_sub",
                        "videosub",
                        "stream2",
                        "live2",
                    )
                )
            paths.sort(key=lambda p: 0 if is_sub(p) else 1)
        out.extend(paths)
    return out


# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------


class SmartRTSPService:
    """High-level: probe(...) returns a SmartProbeResult."""

    def probe(self, req: SmartProbeRequest) -> ProbeResult:
        steps: list[Step] = []

        # ---------- Case A: user gave a URL ----------
        if req.rtsp_url:
            return self._probe_with_url(req, steps)

        # ---------- Case B: user gave host + credentials ----------
        if not req.host or not req.username:
            return ProbeResult(
                ok=False,
                strategy="invalid_request",
                summary="No URL or credentials given.",
                suggestion="Provide an RTSP URL or (host + username + password).",
            )
        return self._probe_with_credentials(req, steps)

    # --- Path A: explicit URL --------------------------------------------------

    def _probe_with_url(self, req: SmartProbeRequest, steps: list[Step]) -> ProbeResult:
        url = req.rtsp_url or ""
        try:
            parts = urlsplit(url)
        except Exception as exc:
            return ProbeResult(
                ok=False,
                strategy="user_url",
                summary=f"Cannot parse URL: {exc}",
                steps=steps,
                suggestion="The URL is malformed. Check the scheme and host.",
            )
        host = parts.hostname or ""
        port = parts.port or (322 if parts.scheme == "rtsps" else 554)
        if not host:
            return ProbeResult(
                ok=False,
                strategy="user_url",
                summary="URL has no host.",
                steps=steps,
                suggestion="Add the camera IP after the scheme: rtsp://USER:PASS@HOST:PORT/path",
            )

        # Step 1: TCP probe
        s_tcp = _tcp_probe(host, port)
        steps.append(s_tcp)
        if not s_tcp.ok:
            return ProbeResult(
                ok=False,
                strategy="user_url",
                summary=f"Cannot reach {host}:{port}.",
                steps=steps,
                suggestion=s_tcp.error,
            )

        # Step 2: RTSP DESCRIBE
        t0 = time.monotonic()
        code, body = _rtsp_describe(url, timeout=req.probe_timeout_seconds / 3)
        dt = int((time.monotonic() - t0) * 1000)
        if code == 200:
            steps.append(Step("rtsp_describe", True, dt, "RTSP DESCRIBE returned 200 OK"))
        elif code == 401:
            steps.append(Step("rtsp_describe", False, dt, "RTSP DESCRIBE returned 401 (auth failed)"))
            return ProbeResult(
                ok=False,
                strategy="user_url",
                summary="The URL path is correct, but the camera rejected the credentials.",
                steps=steps,
                suggestion="Double-check username and password (case-sensitive). Special characters like '@' must be URL-encoded as '%40'.",
            )
        elif code == 404:
            steps.append(Step("rtsp_describe", False, dt, "RTSP DESCRIBE returned 404 (path not found)"))
            return ProbeResult(
                ok=False,
                strategy="user_url",
                summary="The camera is reachable but the URL path is wrong.",
                steps=steps,
                suggestion="Try Smart Connect with just the host + credentials — we'll auto-discover the right URL.",
            )
        elif code != 0:
            steps.append(Step("rtsp_describe", False, dt, f"RTSP DESCRIBE returned {code}", error=body[:200]))
        else:
            # 0 = transport failure — could be TLS mismatch
            steps.append(Step("rtsp_describe", False, dt, "Transport error on DESCRIBE", error=body))

        # Step 3: full OpenCV open + first frame (the real test)
        t0 = time.monotonic()
        outcome = probe_rtsp(url, timeout_ms=req.probe_timeout_seconds * 1000)
        dt = int((time.monotonic() - t0) * 1000)
        if outcome.ok:
            steps.append(
                Step(
                    "open_stream",
                    True,
                    dt,
                    f"OpenCV opened the stream and read a {outcome.width}x{outcome.height} frame",
                )
            )
            return ProbeResult(
                ok=True,
                strategy="user_url",
                summary=f"Connected to {host}:{port} — stream is live.",
                working_url=url,
                width=outcome.width,
                height=outcome.height,
                steps=steps,
            )
        steps.append(
            Step(
                "open_stream",
                False,
                dt,
                "OpenCV could not open the stream",
                error=outcome.error or "unknown",
            )
        )

        suggestion = self._suggest_for_failure(host, port, code, outcome.error, parts.scheme)
        return ProbeResult(
            ok=False,
            strategy="user_url",
            summary=f"Could not open the stream at {host}:{port}.",
            steps=steps,
            suggestion=suggestion,
        )

    # --- Path B: host + credentials -------------------------------------------

    def _probe_with_credentials(self, req: SmartProbeRequest, steps: list[Step]) -> ProbeResult:
        host = req.host  # type: ignore[assignment]
        port = req.port
        user = req.username or ""
        pwd = req.password or ""

        # Step 1: TCP preflight
        s_tcp = _tcp_probe(host, port)
        steps.append(s_tcp)
        if not s_tcp.ok:
            return ProbeResult(
                ok=False,
                strategy="onvif_discovery",
                summary=f"Cannot reach {host}:{port}.",
                steps=steps,
                suggestion=s_tcp.error,
            )

        # Step 1b: NON-RTSP-PORT GUARDRAIL.
        # If the user-supplied port is not the standard RTSP port (554) and
        # not the standard RTSPS port (322), we sanity-check by ALSO probing
        # port 554. If 554 is open, the user most likely typed the wrong port
        # (e.g. they pasted a Hikvision SDK port 8000 or a web UI port 8080
        # that they saw in a port scanner). Fall back to 554 transparently
        # rather than running 22 candidate paths against the wrong service —
        # which the camera resets and the operator sees as a meaningless
        # "Tried 25 brand-specific paths, none worked".
        if port not in (554, 322):
            s_alt = _tcp_probe(host, 554, timeout=2.0)
            if s_alt.ok:
                steps.append(
                    Step(
                        "port_correction",
                        True,
                        s_alt.duration_ms,
                        f"Port {port} is open but not RTSP. Standard RTSP "
                        f"port 554 is ALSO open on {host} — switching to "
                        f"554 for the discovery ladder.",
                    )
                )
                port = 554
            else:
                steps.append(
                    Step(
                        "port_correction",
                        False,
                        s_alt.duration_ms,
                        f"Port {port} was provided but standard RTSP port "
                        f"554 is also unreachable — continuing with {port} "
                        f"anyway.",
                        error=s_alt.error,
                    )
                )

        # Step 2: TLS detection (informational — we still try plain first)
        s_tls = _tls_detect(host, port)
        steps.append(s_tls)
        needs_tls = s_tls.ok and "RTSPS" in s_tls.detail

        # Step 3: ONVIF discovery (the most reliable strategy)
        t0 = time.monotonic()
        onvif = _onvif_discover(host, user, pwd, timeout=req.probe_timeout_seconds / 2)
        dt = int((time.monotonic() - t0) * 1000)
        vendor_hint: str | None = None
        if onvif["ok"]:
            mfr = (onvif.get("manufacturer") or "").strip()
            model = (onvif.get("model") or "").strip()
            vendor_hint = (mfr + (f" {model}" if model else "")).strip() or None
            steps.append(
                Step(
                    "onvif_discovery",
                    True,
                    dt,
                    f"ONVIF returned {len(onvif['profiles'])} profile(s) — {vendor_hint or 'unknown vendor'}",
                )
            )

            profile = _pick_profile(onvif["profiles"], req.prefer_sub_stream)
            onvif_url = _inject_credentials(profile["uri"], user, pwd)
            # If TLS detection said RTSPS-required, upgrade rtsp:// → rtsps://
            if needs_tls and onvif_url.startswith("rtsp://"):
                onvif_url = "rtsps://" + onvif_url[len("rtsp://") :]

            t0 = time.monotonic()
            outcome = probe_rtsp(onvif_url, timeout_ms=req.probe_timeout_seconds * 1000)
            dt = int((time.monotonic() - t0) * 1000)
            if outcome.ok:
                steps.append(
                    Step(
                        "open_stream",
                        True,
                        dt,
                        f"Opened ONVIF-discovered stream ({outcome.width}x{outcome.height})",
                    )
                )
                return ProbeResult(
                    ok=True,
                    strategy="onvif_discovery",
                    summary=f"Connected via ONVIF — {vendor_hint or 'unknown vendor'}.",
                    working_url=onvif_url,
                    width=outcome.width,
                    height=outcome.height,
                    vendor_hint=vendor_hint,
                    steps=steps,
                )
            steps.append(
                Step(
                    "open_stream",
                    False,
                    dt,
                    "ONVIF gave us a URL but OpenCV could not open it",
                    error=outcome.error,
                )
            )
            # Fall through to vendor fallbacks below
        else:
            steps.append(
                Step(
                    "onvif_discovery",
                    False,
                    dt,
                    "ONVIF unavailable",
                    error=onvif.get("error"),
                )
            )

        # Step 4: brand path fallbacks
        mfr = (onvif.get("manufacturer") or "").lower() if isinstance(onvif, dict) else ""
        vendor_key = None
        for needle, key in _VENDOR_LOOKUP.items():
            if needle in mfr:
                vendor_key = key
                break
        candidates = _candidate_paths_for_vendor(
            vendor_key, prefer_sub=req.prefer_sub_stream
        )
        scheme = "rtsps" if needs_tls else "rtsp"
        attempts = 0
        creds_rejected_count = 0
        last_error: str | None = None
        # Bound total fallback time so we don't keep banging on a permanently
        # broken camera for minutes. Reserve a couple of seconds for the
        # final response — the operator gets a definitive "no" within
        # probe_timeout_seconds of clicking Connect.
        deadline = time.monotonic() + max(5, req.probe_timeout_seconds - 2)
        for tpl in candidates:
            if time.monotonic() >= deadline:
                steps.append(
                    Step(
                        "vendor_fallback",
                        False,
                        0,
                        f"Aborted after {attempts} attempt(s) — probe timeout reached",
                    )
                )
                return ProbeResult(
                    ok=False,
                    strategy="vendor_fallback",
                    summary="Probe timed out before finding a working URL.",
                    steps=steps,
                    suggestion=(
                        "Try again with a longer timeout, or open the camera's web UI "
                        "in a browser to find the exact RTSP path and paste it in 'Advanced URL' mode."
                    ),
                )
            # Build the URL — replace the scheme prefix if TLS required
            if needs_tls:
                tpl_to_use = tpl.replace("rtsp://", "rtsps://", 1)
            else:
                tpl_to_use = tpl
            built = _build_url(tpl_to_use, ip=host, port=port, user=user, pwd=pwd)
            # DESCRIBE first — cheap path validation.
            code, body = _rtsp_describe(built, timeout=4.0)
            attempts += 1

            # 401 is the camera's auth-required CHALLENGE, not a rejection.
            # The DESCRIBE we send carries no Authorization header, so a
            # camera that requires auth ALWAYS returns 401 on the first try.
            # Treat 401 exactly like 200 — promote to a full OpenCV open,
            # which handles Basic + Digest auth natively via the user:pass
            # URL. OpenCV failure on a 401-challenged path is the true
            # "credentials rejected" signal.
            if code not in (200, 401):
                # 404 / 0 / 5xx — wrong path or transport error; try next.
                last_error = f"{code} on {_redact(built)}" if code else body[:80]
                continue

            # Promote to OpenCV.
            t0 = time.monotonic()
            outcome = probe_rtsp(built, timeout_ms=req.probe_timeout_seconds * 1000)
            dt = int((time.monotonic() - t0) * 1000)
            if outcome.ok:
                steps.append(
                    Step(
                        "vendor_fallback",
                        True,
                        dt,
                        f"Vendor pattern matched after {attempts} attempt(s): "
                        f"{_redact(built)} ({outcome.width}x{outcome.height})",
                    )
                )
                return ProbeResult(
                    ok=True,
                    strategy="vendor_fallback",
                    summary=f"Connected via vendor pattern ({vendor_key or 'generic'}).",
                    working_url=built,
                    width=outcome.width,
                    height=outcome.height,
                    vendor_hint=vendor_hint,
                    steps=steps,
                )

            # OpenCV failed. Track separately whether this was on a 401
            # (likely creds wrong) vs 200 (creds maybe OK but codec/path
            # quirk). After loop, decide which message to surface.
            last_error = outcome.error
            if code == 401:
                creds_rejected_count += 1
            # Keep trying — could be a sub-stream vs main-stream mismatch
            # or a codec issue on this path that doesn't affect others.

        # Loop exhausted without success.
        # If MOST of the path attempts that reached the auth layer returned
        # 401 → creds are likely wrong. Otherwise it's a generic path/codec
        # discovery failure.
        if creds_rejected_count >= 3 and attempts >= 3:
            steps.append(
                Step(
                    "vendor_fallback",
                    False,
                    0,
                    f"All {creds_rejected_count} reachable paths returned 401 — credentials rejected",
                )
            )
            return ProbeResult(
                ok=False,
                strategy="vendor_fallback",
                summary="Camera rejected the credentials.",
                steps=steps,
                suggestion=(
                    "Username/password is wrong. Check exact case (Admin@123 vs "
                    "admin@123 are different) and verify by opening the camera's "
                    "web UI in a browser."
                ),
            )

        steps.append(
            Step(
                "vendor_fallback",
                False,
                0,
                f"Tried {attempts} brand-specific paths, none worked",
                error=last_error,
            )
        )
        return ProbeResult(
            ok=False,
            strategy="vendor_fallback",
            summary="Could not discover a working stream URL automatically.",
            steps=steps,
            suggestion=(
                "Open the camera's web UI in a browser, log in, and look under "
                "Settings → Network → RTSP for the exact URL. Then paste it here "
                "in 'Advanced URL' mode."
            ),
        )

    # --- Failure-mode suggestions ---------------------------------------------

    def _suggest_for_failure(
        self,
        host: str,
        port: int,
        describe_code: int,
        opencv_error: str | None,
        scheme: str,
    ) -> str:
        err = (opencv_error or "").lower()
        if "401" in err or describe_code == 401:
            return "Authentication failed. Verify the username/password — they are case-sensitive."
        if "404" in err or describe_code == 404:
            return "The URL path is wrong. Try Smart Connect with just the host + credentials so we can auto-discover."
        if "invalid data" in err and scheme == "rtsp":
            return f"Camera at {host}:{port} may require RTSPS (TLS). Try changing the scheme from rtsp:// to rtsps://."
        if "timeout" in err or "timed out" in err:
            return "Camera is reachable but didn't deliver a frame. The stream may be configured for a codec OpenCV doesn't support, or the camera is overloaded. Try the sub stream instead."
        return "Stream could not be decoded. Check that the camera's web UI shows a live image, then try Smart Connect for auto-discovery."


# Process-wide singleton (the service is stateless, this just saves allocations).
_INSTANCE: SmartRTSPService | None = None


def get_smart_rtsp_service() -> SmartRTSPService:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SmartRTSPService()
    return _INSTANCE

"""LAN camera discovery — ONVIF WS-Discovery + ARP/ping fallback.

Two strategies:

1. ONVIF WS-Discovery (preferred): UDP multicast Probe to
   `239.255.255.250:3702`. Conforming cameras respond with their
   ONVIF XAddrs URL, from which we extract IP + manufacturer hints.
   This is the standard mechanism every modern ONVIF camera supports.

2. Subnet scan fallback: parallel TCP-probe ports 554, 80, 8000 on
   every IP in the local /24. Any IP that opens 554 is treated as a
   likely RTSP camera. Slower but works when ONVIF discovery is off
   (some Hikvision firmware ships with it disabled by default).

Both strategies emit the same `DiscoveredCamera` dataclass so the API
layer can present a unified list. Discovery never persists a camera —
the operator confirms via Smart Connect, which validates credentials.
"""
from __future__ import annotations

import socket
import struct
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse

from app.core.logger import get_logger

log = get_logger(__name__)


@dataclass
class DiscoveredCamera:
    ip: str
    source: str  # "onvif" | "tcp_scan"
    onvif_url: str | None = None
    rtsp_port: int = 554
    web_port: int = 80
    vendor_hint: str | None = None
    raw_signature: str = ""
    notes: list[str] = field(default_factory=list)


_WS_DISCOVERY_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:{message_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""


def _local_ipv4_interfaces() -> list[str]:
    """Return list of local IPv4 addresses on UP interfaces.

    Used so we can bind multicast send sockets to the right interface
    — Windows otherwise sends WS-Discovery only on the default route,
    which is often the office WiFi rather than the camera LAN.
    """
    out: list[str] = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("169.254.") and addr != "127.0.0.1":
                if addr not in out:
                    out.append(addr)
    except Exception as exc:
        log.warning("Could not enumerate local interfaces: %s", exc)
    return out


def _ws_discovery(timeout: float = 4.0) -> list[DiscoveredCamera]:
    """Send a Probe to 239.255.255.250:3702 from each local interface,
    collect responses for `timeout` seconds, parse out XAddrs.

    Returns one DiscoveredCamera per responding device. Cameras typically
    return their HTTP ONVIF endpoint as the XAddr — e.g.
    `http://192.168.1.108:8000/onvif/device_service`.
    """
    discovered: dict[str, DiscoveredCamera] = {}
    interfaces = _local_ipv4_interfaces() or [""]  # fall back to default

    for iface in interfaces:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if iface:
                # Bind to this interface so the multicast goes out the right NIC
                sock.bind((iface, 0))
            # Set the multicast outgoing interface
            if iface:
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(iface),
                )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(timeout)

            probe = _WS_DISCOVERY_TEMPLATE.format(message_id=uuid.uuid4())
            sock.sendto(probe.encode("utf-8"), ("239.255.255.250", 3702))

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    sock.settimeout(max(0.1, deadline - time.monotonic()))
                    data, addr = sock.recvfrom(65536)
                except socket.timeout:
                    break
                except OSError:
                    break
                body = data.decode("utf-8", errors="ignore")
                # Naive but effective XAddrs extraction — most responses
                # contain `<d:XAddrs>http://...</d:XAddrs>`. We just grep
                # the URL substring rather than parsing SOAP.
                ip = addr[0]
                if ip in discovered:
                    continue
                cam = DiscoveredCamera(ip=ip, source="onvif", raw_signature=body[:300])
                # Try to extract the ONVIF service URL
                import re
                m = re.search(r"<\w*:?XAddrs>([^<]+)</\w*:?XAddrs>", body)
                if m:
                    cam.onvif_url = m.group(1).strip().split()[0]
                    try:
                        parsed = urlparse(cam.onvif_url)
                        cam.web_port = parsed.port or 80
                    except Exception:
                        pass
                # Sniff manufacturer hint from response body
                low = body.lower()
                for needle, hint in (
                    ("hikvision", "Hikvision"),
                    ("dahua", "Dahua"),
                    ("axis", "Axis"),
                    ("bosch", "Bosch"),
                    ("vivotek", "Vivotek"),
                    ("hanwha", "Hanwha"),
                    ("reolink", "Reolink"),
                    ("foscam", "Foscam"),
                ):
                    if needle in low:
                        cam.vendor_hint = hint
                        break
                discovered[ip] = cam
            sock.close()
        except Exception as exc:
            log.debug("WS-Discovery on iface %s failed: %s", iface or "default", exc)

    return list(discovered.values())


def _tcp_probe(host: str, port: int, timeout: float = 0.3) -> bool:
    """Quick TCP open check — returns True if the port accepted a connection."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def _subnet_scan(
    subnets: Iterable[str], timeout: float = 0.3
) -> list[DiscoveredCamera]:
    """Parallel TCP scan for port 554 + 80 on every IP in given /24 subnets.

    `subnets` are CIDR-less strings like `192.168.1.` (last octet open).
    Used as a fallback when WS-Discovery returns nothing — typical when
    cameras have ONVIF disabled or are on a different multicast domain.

    Tuning:
      - timeout=0.3s: any LAN camera responds in <50 ms; 300 ms is generous
        and 40 % faster than the old 0.5 s budget.
      - 128 workers (was 64): on a multi-NIC dev box we scan 3-4 /24s
        = 1000+ IPs. Doubling concurrency cuts wall-clock roughly in half
        without meaningfully more CPU (TCP probes are I/O-bound).
    """
    targets: list[str] = []
    for net in subnets:
        for i in range(1, 255):
            targets.append(f"{net}{i}")

    discovered: list[DiscoveredCamera] = []
    with ThreadPoolExecutor(max_workers=128) as pool:
        futures = {
            pool.submit(_tcp_probe, ip, 554, timeout): ip for ip in targets
        }
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                if fut.result():
                    cam = DiscoveredCamera(ip=ip, source="tcp_scan")
                    # Also poke 80 + 8000 to label web UI / SDK availability.
                    # Use a tighter 150 ms timeout — by this point we know
                    # 554 is open on this host, so the host is alive and
                    # any other open port responds fast.
                    if _tcp_probe(ip, 80, timeout=0.15):
                        cam.notes.append("web UI on port 80")
                    if _tcp_probe(ip, 8000, timeout=0.15):
                        cam.notes.append("ISAPI / SDK on port 8000")
                    discovered.append(cam)
            except Exception:
                pass
    return discovered


def discover_cameras(
    *,
    include_subnet_scan: bool = True,
    extra_subnets: Iterable[str] = (),
    ws_timeout: float = 4.0,
) -> list[DiscoveredCamera]:
    """Top-level entry: ONVIF probe + optional fallback TCP scan.

    Always returns the ONVIF-found cameras first (more trustworthy —
    they self-identified). Then merges in TCP-scan results that
    weren't already covered.

    `extra_subnets` lets the caller force-scan additional /24s beyond
    the local interfaces' subnets — e.g. when the AI PC is on the
    office LAN but cameras live on 192.168.1.x.
    """
    out: list[DiscoveredCamera] = []
    seen: set[str] = set()

    # Phase 1: ONVIF multicast
    for cam in _ws_discovery(timeout=ws_timeout):
        if cam.ip not in seen:
            out.append(cam)
            seen.add(cam.ip)
    log.info("ONVIF discovery found %d device(s)", len(out))

    # Phase 2: subnet TCP scan
    if include_subnet_scan:
        subnets: list[str] = []
        for ip in _local_ipv4_interfaces():
            parts = ip.split(".")
            if len(parts) == 4:
                subnets.append(".".join(parts[:3]) + ".")
        for s in extra_subnets:
            if s not in subnets:
                subnets.append(s.rstrip(".") + ".")

        # Always also try the camera-default 192.168.1.x because some
        # installs set the AI PC's IP on a different subnet from the
        # cameras (multiple NICs).
        if "192.168.1." not in subnets:
            subnets.append("192.168.1.")

        for cam in _subnet_scan(subnets):
            if cam.ip not in seen:
                out.append(cam)
                seen.add(cam.ip)
        log.info("Total devices after TCP scan: %d", len(out))

    return out

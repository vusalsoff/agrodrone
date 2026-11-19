"""Honest network diagnostics for Mode A (Local Dev) vs Mode B (Dual-Homed Remote Cloud)."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class NetworkDiagnostics:
    camera_host_reachable: bool
    api_host_reachable: bool
    internet_reachable: bool
    deployment_mode: str
    single_wifi_warning: str | None


def _tcp_probe(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def inspect_network_state(
    *,
    esp32_stream_url: str,
    api_base_url: str,
    deployment_mode: str,
) -> NetworkDiagnostics:
    cam_parsed = urlparse(esp32_stream_url)
    cam_host = cam_parsed.hostname or "192.168.4.1"
    cam_port = cam_parsed.port or 81

    api_parsed = urlparse(api_base_url)
    api_host = api_parsed.hostname or "127.0.0.1"
    api_port = api_parsed.port or (443 if api_parsed.scheme == "https" else 80)

    camera_ok = _tcp_probe(cam_host, cam_port, timeout=1.5)
    api_ok = _tcp_probe(api_host, api_port, timeout=1.5)
    # Check public DNS port 53 (no HTTP body, fast TCP reachability check)
    internet_ok = _tcp_probe("1.1.1.1", 53, timeout=1.5)

    warning: str | None = None
    if deployment_mode == "remote_cloud" and camera_ok and not internet_ok:
        warning = (
            "Connected to local camera subnet (192.168.4.x) without internet uplink. "
            "A single Wi-Fi adapter cannot join 'agroDrone' and a Wi-Fi router simultaneously; "
            "use a second uplink adapter (USB LTE / Ethernet / second Wi-Fi) or Mode A (local_dev)."
        )

    return NetworkDiagnostics(
        camera_host_reachable=camera_ok,
        api_host_reachable=api_ok,
        internet_reachable=internet_ok,
        deployment_mode=deployment_mode,
        single_wifi_warning=warning,
    )

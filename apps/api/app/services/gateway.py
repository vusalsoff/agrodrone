"""Hardware capability manifest and isolated ESP32-CAM Edge Gateway policy."""

from __future__ import annotations

from app.core.config import Settings
from app.schemas.system import (
    HardwareDeviceSpec,
    ModuleReadinessItem,
    NetworkBoundaryPolicy,
)


def get_hardware_baseline(settings: Settings) -> list[HardwareDeviceSpec]:
    """Return the factual hardware baseline without fabricated sensors or telemetry."""
    return [
        HardwareDeviceSpec(
            id="esp32-cam-ov2640",
            name="AI Thinker ESP32-CAM (OV2640)",
            category="camera_module",
            connectivity_mode="isolated_ap",
            local_ssid=settings.esp32_default_ap_ssid,
            local_dashboard_url=settings.esp32_default_base_url,
            local_stream_url=settings.esp32_default_stream_url,
            cloud_directly_reachable=False,
            supported_capabilities=[
                "Local Wi-Fi Access Point (SSID: agroDrone, IP: 192.168.4.1)",
                "Local web control UI (http://192.168.4.1)",
                "Local MJPEG stream (http://192.168.4.1:81/stream)",
                "RGB still capture & streaming via OV2640 sensor",
            ],
            unsupported_capabilities=[
                "Direct public cloud reachability from internet servers",
                "Onboard GPS/RTK geotagging",
                "Multispectral / Near-Infrared (NIR) true NDVI sensing",
                "Digital battery voltage or thermal telemetry API",
            ],
        ),
        HardwareDeviceSpec(
            id="e88-airframe",
            name="E88 Dual-Camera Drone Airframe",
            category="airframe",
            connectivity_mode="manual_rf",
            cloud_directly_reachable=False,
            supported_capabilities=[
                "Manual visual line-of-sight aerial platform",
                "Payload carrier for lightweight optical inspection",
            ],
            unsupported_capabilities=[
                "MAVLink / DroneKit / SDK telemetry link",
                "Autonomous GPS waypoint flight execution",
                "Real-time altitude, airspeed, heading, or battery telemetry",
                "Programmatic gimbal orientation feedback",
            ],
        ),
        HardwareDeviceSpec(
            id="esp32-cam-mb",
            name="ESP32-CAM-MB USB Programmer",
            category="programmer",
            connectivity_mode="usb_serial_bench",
            cloud_directly_reachable=False,
            supported_capabilities=[
                "USB-to-UART firmware flashing",
                "Bench serial console diagnostics",
            ],
            unsupported_capabilities=[
                "In-flight telemetry or wireless bridging",
            ],
        ),
        HardwareDeviceSpec(
            id="usb-power-source",
            name="Portable USB Power Source",
            category="power_source",
            connectivity_mode="unmanaged_power",
            cloud_directly_reachable=False,
            supported_capabilities=[
                "Portable 5V power delivery to ESP32-CAM module",
            ],
            unsupported_capabilities=[
                "Remote battery percentage or voltage reporting",
            ],
        ),
    ]


def get_network_boundary_policy(settings: Settings) -> NetworkBoundaryPolicy:
    """Return honest ESP32-CAM network isolation policy and gateway readiness."""
    return NetworkBoundaryPolicy(
        esp32_ap_ssid=settings.esp32_default_ap_ssid,
        esp32_dashboard_url=settings.esp32_default_base_url,
        esp32_mjpeg_stream_url=settings.esp32_default_stream_url,
        direct_cloud_probe_allowed=settings.allow_direct_local_camera_probe,
        gateway_status="offline" if settings.edge_gateway_enabled else "not_deployed_phase_4",
        explanation=(
            "The ESP32-CAM operates as an isolated Wi-Fi Access Point on private subnet "
            "192.168.4.0/24. Remote servers cannot directly reach 192.168.4.1. Operators can now "
            "upload captured imagery in Phase 2 via /media; Phase 3 adds server-side YOLO detection "
            "and Phase 4 adds the outbound-authenticated Field Edge Gateway."
        ),
    )


def get_module_readiness() -> list[ModuleReadinessItem]:
    """Return honest Phase 2 status across all platform modules."""
    return [
        ModuleReadinessItem(
            id="overview",
            name="Overview Dashboard",
            route="/",
            phase="Phase 2",
            status="foundation_active",
            summary="Live API health, real database operational counts, hardware boundary, and module status.",
        ),
        ModuleReadinessItem(
            id="fields",
            name="Field Management",
            route="/fields",
            phase="Phase 2",
            status="foundation_active",
            summary="Full parcel CRUD, GeoJSON polygon validation, geodesic hectare calculation, and ownership RBAC.",
        ),
        ModuleReadinessItem(
            id="maps",
            name="Interactive Field Maps",
            route="/maps",
            phase="Phase 2",
            status="foundation_active",
            summary="MapLibre GL interactive GeoJSON polygon creation, vertex editing, deletion, and saved parcel rendering.",
        ),
        ModuleReadinessItem(
            id="devices",
            name="Device Management",
            route="/devices",
            phase="Phase 2",
            status="foundation_active",
            summary="Real hardware CRUD with ESP32-CAM isolated AP config and verified-contact-only online policy.",
        ),
        ModuleReadinessItem(
            id="missions",
            name="Mission Management",
            route="/missions",
            phase="Phase 2",
            status="foundation_active",
            summary="Manual mission CRUD, validated lifecycle transitions, timestamped observations, and media attachment.",
        ),
        ModuleReadinessItem(
            id="media",
            name="Media Library",
            route="/media",
            phase="Phase 2",
            status="foundation_active",
            summary="Magic-byte verified image/video uploads, local & private S3/MinIO storage, preview gallery, authorized downloads.",
        ),
        ModuleReadinessItem(
            id="settings",
            name="User Settings",
            route="/settings",
            phase="Phase 2",
            status="foundation_active",
            summary="Session management, Admin RBAC user roles, immutable audit log viewer, and design system reference.",
        ),
        ModuleReadinessItem(
            id="detection",
            name="AI Detection",
            route="/detection",
            phase="Phase 3",
            status="foundation_active",
            summary="Real Ultralytics YOLOv8n + PyTorch + OpenCV image & sampled-video inference with annotated output.",
        ),
        ModuleReadinessItem(
            id="history",
            name="Detection History",
            route="/history",
            phase="Phase 3",
            status="foundation_active",
            summary="Full job history, search/filtering, human review (confirm/reject/uncertain), and JSON/annotated exports.",
        ),
        ModuleReadinessItem(
            id="monitoring",
            name="Live Monitoring",
            route="/monitoring",
            phase="Phase 4",
            status="foundation_active",
            summary="Authenticated ESP32-CAM Edge Gateway relay, snapshot capture, diagnostics, and YOLOv8n snapshot analysis.",
        ),
        ModuleReadinessItem(
            id="alerts",
            name="Alerts & Notifications",
            route="/alerts",
            phase="Phase 5",
            status="foundation_active",
            summary="Configurable alert rules, deduplication/cooldowns, gateway offline TTL alerts, and in-app notification center.",
        ),
        ModuleReadinessItem(
            id="reports",
            name="Reports & Analytics",
            route="/reports",
            phase="Phase 5",
            status="foundation_active",
            summary="Database-backed analytics dashboard and exportable PDF, CSV, and JSON reports with full model provenance.",
        ),
    ]

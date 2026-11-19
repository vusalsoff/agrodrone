# ESP32-CAM & Field Edge Gateway Specification

## 1. Current Hardware Baseline

- **Airframe:** E88 dual-camera drone (manual flight control, no open telemetry SDK / MAVLink bus)
- **Imaging Module:** AI Thinker ESP32-CAM with OV2640 RGB sensor
- **Programmer:** ESP32-CAM-MB (USB-to-UART bench flashing)
- **Power:** Portable USB power source (no digital charge telemetry)
- **Current Network Mode:** Standalone Wi-Fi Access Point
  - **SSID:** `agroDrone`
  - **Camera Control UI:** `http://192.168.4.1`
  - **MJPEG Stream Endpoint:** `http://192.168.4.1:81/stream`

---

## 2. Why Direct Cloud Connectivity Is Impossible (and Unsafe)

`192.168.4.1` is an RFC-1918 private address served exclusively by the ESP32-CAM softAP subnet.

1. A cloud-deployed AgroDrone API cannot open TCP sockets to `192.168.4.1`.
2. A browser connected to the public internet (to load a cloud-hosted AgroDrone dashboard) is typically not simultaneously connected to the `agroDrone` Wi-Fi AP, and even when it is, modern browsers block mixed-content (`https://` page loading `http://192.168.4.1:81/stream`) and Private Network Access (PNA) requests without explicit local gateway handling.
3. Allowing a backend server to fetch user-supplied private IP URLs creates a Server-Side Request Forgery (SSRF) vulnerability.

Therefore, AgroDrone enforces:
- `ALLOW_DIRECT_LOCAL_CAMERA_PROBE=false` in all server deployments.
- Explicit device `connectivity_mode`: `isolated_ap` (current), `manual_import` (Phase 3), or `edge_gateway` (Phase 4).

---

## 3. Target Field Edge Gateway Architecture (Phase 4)

The **Field Edge Gateway** (`services/edge-gateway`) is a lightweight local companion service running on an operator's field laptop or Raspberry Pi near the drone flight area.

### 3.1 Network Dual-Homing or Store-and-Forward

- **Mode A — Live Dual-Homed Relay:**
  - Interface 1 (`wlan0`): Associated with `agroDrone` Wi-Fi AP (`192.168.4.x`)
  - Interface 2 (`wwan0` / USB cellular tether / `wlan1`): Internet uplink to AgroDrone Cloud API over HTTPS/WSS
- **Mode B — Offline Store-and-Forward (Recommended for Remote Fields):**
  - Connects to `agroDrone`, pulls frames/snapshots locally into an encrypted local queue (`SQLite + local spool directory`) tagged with operator-selected `field_id`, `mission_id`, and optional handheld GPS coordinates.
  - When internet connectivity is restored, uploads queued frames to S3 via FastAPI presigned URLs and reconciles metadata idempotently using SHA-256 content digests.

### 3.2 Outbound Gateway Protocol Contract

All gateway traffic is **outbound-only** (no port forwarding or public IP required on the field device):

1. **Provisioning:** Admin generates a one-time enrollment token in AgroDrone → gateway exchanges it for a scoped `gateway_token` (or mTLS client certificate).
2. **Heartbeat (`POST /api/v1/gateway/heartbeat`):** Reports gateway uptime, local reachability of `192.168.4.1`, observed camera frame rate, dropped frames, and local disk queue depth.
3. **Frame Upload (`POST /api/v1/media/presign` → `PUT <S3>` → `POST /api/v1/media/commit`):** Uploads raw JPEG frames directly to S3-compatible storage with SHA-256 verification.
4. **Live Preview Stream (Optional when uplink permits):** Gateway throttles MJPEG frames (e.g., 1–3 FPS JPEG frames or WebRTC/H.264 stream via MediaMTX/LiveKit) over an authenticated WSS/WHIP session so remote operators can inspect imagery securely over TLS.

---

## 4. OV2640 Imaging Constraints Relevant to AI

- OV2640 captures **RGB** frames (max 1600×1200 UXGA; typical stable Wi-Fi streaming is VGA `640×480` or SVGA `800×600` to avoid thermal throttling and frame drops).
- Motion blur, rolling-shutter vibration from lightweight airframes, and low pixel density at high altitudes severely impact small-object detection (e.g., insects, snakes, leaf-level lesions).
- High-accuracy detection of small agricultural anomalies requires controlled low-altitude still captures (UXGA/SXGA JPEG), dataset curation from the actual OV2640 optical characteristics, and quantitative validation prior to operational deployment.

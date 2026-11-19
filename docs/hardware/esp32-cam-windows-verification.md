# ESP32-CAM Real Hardware Verification Procedure (Windows)

This guide covers physical verification of the **AI Thinker ESP32-CAM (OV2640)** running in isolated Wi-Fi Access Point mode (`SSID: agroDrone`, `http://192.168.4.1`, MJPEG `http://192.168.4.1:81/stream`).

> **Scope Honesty:** Automated tests verify MJPEG parsing, offline spooling, credential hashing, replay protection, and stream relay against simulated MJPEG payloads. Physical hardware verification requires executing the steps below with the camera powered on.

---

## Prerequisites
- AI Thinker ESP32-CAM powered via portable 5V USB source (or ESP32-CAM-MB programmer).
- Windows host running AgroDrone API (`http://127.0.0.1:8000`) and Web UI (`http://127.0.0.1:3000`).
- Mode A (`local_dev`): No internet required; Windows Wi-Fi connects to `agroDrone`.
- Mode B (`remote_cloud`): Dedicated Ethernet/USB-tether interface for HTTPS internet + Wi-Fi for `agroDrone`.

## Step-by-Step Verification

1. **Power & AP Check:**
   - Connect Windows Wi-Fi to SSID `agroDrone`.
   - Open `http://192.168.4.1` in a browser and confirm the ESP32-CAM dashboard responds.
2. **Enroll Gateway in AgroDrone:**
   - Sign in to `http://127.0.0.1:3000/devices`, register your ESP32-CAM device if not already present.
   - Navigate to `http://127.0.0.1:3000/monitoring`, click **Enroll Gateway**, and copy the one-time `agw_...` credential and `gateway_id`.
3. **Start the Field Edge Gateway (Mode A):**
   ```powershell
   cd C:\Users\HONOR\.gemini\antigravity\scratch\agrodrone\apps\api
   .\.venv\Scripts\agrodrone-gateway.exe `
     --mode local_dev `
     --api-base-url http://127.0.0.1:8000 `
     --gateway-id <GATEWAY_ID> `
     --gateway-token <AGW_TOKEN>
   ```
4. **Verify Heartbeat & Diagnostics:**
   - Confirm `/monitoring` transitions the gateway status to `Active` with `camera_reachable: true` and real FPS / dropped frame counts.
5. **Verify Live Stream Relay & Snapshot-to-YOLO:**
   - Click **Start Live Relay** in `/monitoring` and verify live MJPEG frames appear.
   - Capture a snapshot, click **Analyze Snapshot (YOLOv8n)**, and verify the resulting `DetectionJob` in `/history/<jobId>`.
6. **Verify Offline Spool Recovery:**
   - Briefly stop the API (`Ctrl+C`), let the gateway capture a snapshot into its local SQLite + disk spool, restart the API, and confirm the spooled snapshot automatically uploads.

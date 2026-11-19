# AgroDrone — ESP32-CAM & Edge Gateway Verification Report

## 1. Hardware Baseline & Constraints
- **Camera:** AI Thinker ESP32-CAM (OV2640 RGB sensor)
- **Wi-Fi AP:** `SSID: agroDrone`, Dashboard `http://192.168.4.1`, MJPEG `http://192.168.4.1:81/stream`
- **Airframe:** E88 Dual-Camera Drone (manual RF; no GPS, altitude, or battery telemetry)

## 2. Automated Verification (`test_edge_gateway.py` & `test_ultimate_master_audit.py`)
- **Result:** `VERIFIED` (Simulated MJPEG & API integration)
  - Multipart MJPEG frame parsing, SOI/EOI validation, and bounded frame byte limits.
  - Offline SQLite + disk snapshot spooling with quota and retry recovery.
  - Gateway enrollment (`agw_...` SHA-256 hashed), credential rotation, revocation, and timestamp+nonce replay protection.
  - Bounded `StreamSession` live relay, TTL expiry, and snapshot-to-YOLOv8n analysis.

## 3. Physical Hardware Verification Status
- **Status:** `BLOCKED` (No physical ESP32-CAM device attached to the audit host).
- **Procedure:** Follow `docs/hardware/esp32-cam-windows-verification.md` on a Windows field laptop connected to `agroDrone` Wi-Fi AP (Mode A) or dual-interface Mode B (`remote_cloud`).

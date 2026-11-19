# ESP32-CAM → AgroDrone AI → Arduino UNO (COM15) Integration

This guide documents how to run the AgroDrone backend AI pipeline, ESP32-CAM capture, and the Arduino UNO USB Serial alert bridge (`COM15`, `9600` baud) together on Windows.

## Hardware Setup
- **Arduino UNO**: Connected via USB Serial on **`COM15`** at **`9600` baud**.
  - `D8`: Green LED (verified clear / `'0'`)
  - `D9`: Red LED (target detected / `'1'`)
  - `D10`: Low-current buzzer (target detected / `'1'`)
  - Existing firmware accepts ASCII `'1'` (detection) and `'0'` (no detection) with a **3-second command timeout** safety fallback.
- **ESP32-CAM**: Connected on local Wi-Fi (`http://192.168.4.1/capture`).

## Safety & Freshness Behavior
- **Target detection (`'1'`)**: Sent at least once per second (`0.5s` default heartbeat) when a fresh (`<= 5.0s`), completed YOLO job contains at least one configured COCO class at or above the confidence threshold.
- **Verified clear (`'0'`)**: Sent at least once per second only when a fresh, completed YOLO job has zero matching detections above the threshold.
- **Fail-safe on failure / stale data**: If the ESP32-CAM, API, AI worker, or `COM15` serial link is unavailable—or if the latest job is incomplete or older than `ARDUINO_MAX_RESULT_AGE_SECONDS`—the bridge **never** reuses stale detections and **never** sends `'0'`. It halts serial transmission so the Arduino's built-in 3-second timeout engages safely.
- **Single-process COM15 lock**: An exclusive OS file lock prevents two bridge instances from opening `COM15` simultaneously.
- **Auto-reconnect**: Temporary USB serial disconnects are caught and automatically reconnected.

## Exact Startup Steps (Windows PowerShell)

1. **Terminal 1 — Start the AgroDrone FastAPI Backend + AI Worker:**
   ```powershell
   cd apps\api
   .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
   ```

2. **Terminal 2 — Enroll an Edge Gateway (one-time) and Start the Arduino Serial Bridge:**
   Enroll a gateway in `/monitoring` (or via API) to obtain your `agw_...` token, then run:
   ```powershell
   $env:AGRODRONE_GATEWAY_TOKEN = "agw_your_enrolled_gateway_token"
   $env:ARDUINO_SERIAL_PORT = "COM15"
   $env:ARDUINO_BAUDRATE = "9600"
   $env:ARDUINO_TARGET_CLASSES = "person,bird,cat,dog,horse,sheep,cow"
   $env:ARDUINO_CONFIDENCE_THRESHOLD = "0.35"

   .\scripts\dev.ps1 -Action arduino
   ```

   Or invoke directly with custom flags:
   ```powershell
   .\apps\api\.venv\Scripts\python.exe -m agrodrone_gateway.arduino_cli `
     --port COM15 --baud 9600 `
     --classes "person,cow,sheep,dog,cat,bird,horse" `
     --confidence 0.35 --heartbeat 0.5 --max-age 5.0
   ```

   Use `--poll-only` if `agrodrone-gateway` or `/monitoring` is already submitting frames and you only want the bridge to poll `GET /api/v1/gateway/latest-detection`.

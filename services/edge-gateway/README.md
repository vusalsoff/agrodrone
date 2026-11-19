# AgroDrone Field Edge Gateway (`services/edge-gateway`)

**Status:** Active in **Phase 4** — Outbound-authenticated ESP32-CAM bridge.

## Network Deployment Modes

### Mode A — Local Development (Single Windows Laptop)
- Connect your Windows computer to the ESP32-CAM Wi-Fi Access Point (`SSID: agroDrone`, camera at `http://192.168.4.1`, MJPEG at `http://192.168.4.1:81/stream`).
- Run the AgroDrone FastAPI backend (`http://127.0.0.1:8000`) and Next.js frontend (`http://127.0.0.1:3000`) locally on the same machine.
- Run `agrodrone-gateway` with `AGRODRONE_API_BASE_URL=http://127.0.0.1:8000`. No internet connection is required.

### Mode B — Remote Cloud (Dual-Interface Field Setup)
- A single Wi-Fi adapter **cannot** stay connected to `agroDrone` (`192.168.4.x`) and an internet Wi-Fi router at the same time.
- Use two interfaces (e.g., laptop built-in Wi-Fi on `agroDrone` + USB cellular/LTE tether or second USB Wi-Fi adapter for internet) OR let the gateway buffer snapshots offline in `GATEWAY_SPOOL_DIR` and drain them automatically once internet uplink returns.
- All traffic to the cloud API is **outbound HTTPS** (`X-Gateway-Token` + replay protection headers). Zero router port forwarding or public ESP32-CAM exposure is ever required.

## Installation & Execution

```powershell
cd apps/api
uv pip install -e "..\..\services\edge-gateway"

# Diagnose local network & camera reachability
.\.venv\Scripts\python.exe -m agrodrone_gateway.cli --diagnose

# Run gateway (paste token issued from /monitoring -> Enroll Gateway)
$env:AGRODRONE_API_BASE_URL = "http://127.0.0.1:8000"
$env:AGRODRONE_GATEWAY_TOKEN = "agw_your_enrolled_token"
$env:AGRODRONE_DEPLOYMENT_MODE = "local_dev"
.\.venv\Scripts\python.exe -m agrodrone_gateway.cli
```

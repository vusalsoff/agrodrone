"""CLI entrypoint for the AgroDrone Phase 4 Field Edge Gateway."""

from __future__ import annotations

import argparse
import logging

from agrodrone_gateway.config import GatewayConfig
from agrodrone_gateway.network import inspect_network_state
from agrodrone_gateway.runner import EdgeGatewayRunner


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agrodrone-gateway",
        description="AgroDrone Phase 4 Field Edge Gateway — Outbound ESP32-CAM Bridge",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Check local ESP32-CAM and API reachability and exit.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Capture one frame from the camera stream, upload/spool it, and exit.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = GatewayConfig.from_env()

    if args.diagnose:
        diag = inspect_network_state(
            esp32_stream_url=cfg.esp32_stream_url,
            api_base_url=cfg.api_base_url,
            deployment_mode=cfg.deployment_mode,
        )
        print(f"Deployment Mode:      {diag.deployment_mode}")
        print(f"Camera Reachable:     {diag.camera_host_reachable} ({cfg.esp32_stream_url})")
        print(f"API Reachable:        {diag.api_host_reachable} ({cfg.api_base_url})")
        print(f"Internet Reachable:   {diag.internet_reachable}")
        if diag.single_wifi_warning:
            print(f"Warning: {diag.single_wifi_warning}")
        return 0

    runner = EdgeGatewayRunner(cfg)
    if args.once:
        runner._send_heartbeat()
        count = runner.run_once_from_stream(max_frames=1, save_snapshot=True)
        print(f"Processed {count} frame(s).")
        runner.api.close()
        return 0

    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

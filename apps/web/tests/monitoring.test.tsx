import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/layout/auth-context";
import { SystemProvider } from "@/components/layout/system-context";
import { MonitoringView } from "@/components/modules/monitoring-view";
import { ToastProvider } from "@/components/ui/toast";
import { apiClient } from "@/lib/api-client";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function setupBaseMocks() {
  vi.spyOn(apiClient, "getMe").mockResolvedValue({
    id: "u-1",
    email: "op@agrodrone.dev",
    full_name: "Field Operator",
    role: "operator",
    is_active: true,
    created_at: "2026-11-19T14:00:00Z",
    updated_at: "2026-11-19T14:00:00Z",
  });
  vi.spyOn(apiClient, "getHealth").mockResolvedValue({
    status: "ok",
    service: "AgroDrone API",
    version: "0.3.0",
    environment: "test",
    database_connected: true,
    database_dialect: "sqlite",
    database_latency_ms: 0.4,
    timestamp: "2026-11-19T14:00:00Z",
  });
  vi.spyOn(apiClient, "getSystemStatus").mockResolvedValue({
    service: "AgroDrone API",
    version: "0.3.0",
    environment: "test",
    phase: "Phase 4",
    database_connected: true,
    database_dialect: "sqlite",
    database_latency_ms: 0.4,
    storage_backend: "local",
    ai_inference_enabled: true,
    edge_gateway_enabled: true,
    counts: {
      fields: 0,
      devices: 1,
      missions: 0,
      media_assets: 0,
      detection_jobs: 0,
      open_alerts: 0,
    },
    subsystems: [],
    timestamp: "2026-11-19T14:00:00Z",
  });
  vi.spyOn(apiClient, "getCapabilities").mockResolvedValue({
    hardware_baseline: [],
    network_boundary: {
      esp32_ap_ssid: "agroDrone",
      esp32_dashboard_url: "http://192.168.4.1",
      esp32_mjpeg_stream_url: "http://192.168.4.1:81/stream",
      direct_cloud_probe_allowed: false,
      gateway_status: "offline",
      explanation: "",
    },
    ai_policy: {
      inference_enabled: true,
      active_model_profile: "yolov8n-coco-general",
      first_working_workflow: "",
      model_honesty_notice: "",
      validated_target_classes: [],
      requires_custom_training_for: [],
    },
    modules: [],
  });
  vi.spyOn(apiClient, "listDevices").mockResolvedValue({
    items: [],
    total: 0,
    limit: 100,
    offset: 0,
  });
}

describe("MonitoringView states and gateway workflows", () => {
  it("renders empty enrollment prompt when no gateways exist", async () => {
    setupBaseMocks();
    vi.spyOn(apiClient, "listGateways").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <SystemProvider>
            <MonitoringView />
          </SystemProvider>
        </AuthProvider>
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Enroll a Field Edge Gateway to Begin/i)).toBeInTheDocument();
    });
  });

  it("displays single-Wi-Fi warning and allows starting a bounded stream", async () => {
    setupBaseMocks();
    const gw = {
      id: "gw-1",
      owner_id: "u-1",
      device_id: null,
      name: "Field Laptop Bridge",
      gateway_identifier: "gw-01",
      deployment_mode: "remote_cloud",
      credential_prefix: "agw_12345678",
      credential_version: 1,
      status: "active",
      is_live: true,
      heartbeat_age_seconds: 2,
      camera_reachable: true,
      camera_fps: 2.1,
      dropped_frames: 0,
      queue_depth: 0,
      queue_bytes: 0,
      internet_reachable: false,
      local_interface: "wlan0",
      uplink_interface: null,
      diagnostics_json: {
        single_wifi_warning: "Single Wi-Fi adapter cannot join agroDrone and internet simultaneously.",
      },
      last_heartbeat_at: "2026-11-19T14:00:00Z",
      revoked_at: null,
      created_at: "2026-11-19T14:00:00Z",
      updated_at: "2026-11-19T14:00:00Z",
    };

    vi.spyOn(apiClient, "listGateways").mockResolvedValue({
      items: [gw],
      total: 1,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(apiClient, "getGatewayDiagnostics").mockResolvedValue({
      gateway: gw,
      active_session: null,
      heartbeat_ttl_seconds: 30,
      network_guidance: "Mode B requires dual interfaces.",
      esp32_ap_ssid: "agroDrone",
      esp32_local_url: "http://192.168.4.1",
      esp32_stream_url: "http://192.168.4.1:81/stream",
      direct_cloud_probe_allowed: false,
    });
    vi.spyOn(apiClient, "listGatewaySnapshots").mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    });
    const startSpy = vi.spyOn(apiClient, "startGatewayStream").mockResolvedValue({
      id: "sess-1",
      gateway_id: "gw-1",
      device_id: null,
      status: "active",
      target_fps: 2,
      max_frame_bytes: 524288,
      frames_relayed: 0,
      expires_at: "2026-11-19T14:05:00Z",
      stopped_at: null,
      last_frame_at: null,
      created_at: "2026-11-19T14:00:00Z",
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <SystemProvider>
            <MonitoringView />
          </SystemProvider>
        </AuthProvider>
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Single Wi-Fi adapter cannot join agroDrone/i)).toBeInTheDocument();
    });

    expect(screen.getByText("2.1 fps")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Start Stream/i }));

    await waitFor(() => {
      expect(startSpy).toHaveBeenCalledWith("gw-1", {
        target_fps: 2,
        max_frame_bytes: 524288,
        duration_seconds: 300,
      });
    });
  });
});

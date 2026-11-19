import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/layout/auth-context";
import { SystemProvider } from "@/components/layout/system-context";
import { OverviewView } from "@/components/modules/overview-view";
import { ToastProvider } from "@/components/ui/toast";
import { apiClient } from "@/lib/api-client";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OverviewView integration with authenticated API client", () => {
  it("renders live subsystem health, user-scoped counts, and honest hardware boundary", async () => {
    vi.spyOn(apiClient, "getMe").mockResolvedValue({
      id: "user-1",
      email: "admin@agrodrone.dev",
      full_name: "Test Admin",
      role: "admin",
      is_active: true,
      created_at: "2026-11-19T14:00:00Z",
      updated_at: "2026-11-19T14:00:00Z",
    });
    vi.spyOn(apiClient, "listFields").mockResolvedValue({ items: [], total: 2, limit: 1, offset: 0 });
    vi.spyOn(apiClient, "listDevices").mockResolvedValue({ items: [], total: 1, limit: 1, offset: 0 });
    vi.spyOn(apiClient, "listMissions").mockResolvedValue({ items: [], total: 3, limit: 1, offset: 0 });
    vi.spyOn(apiClient, "listMedia").mockResolvedValue({ items: [], total: 4, limit: 1, offset: 0 });

    vi.spyOn(apiClient, "getHealth").mockResolvedValue({
      status: "ok",
      service: "AgroDrone API",
      version: "0.2.0",
      environment: "test",
      database_connected: true,
      database_dialect: "sqlite",
      database_latency_ms: 0.4,
      timestamp: "2026-11-19T14:00:00Z",
    });

    vi.spyOn(apiClient, "getSystemStatus").mockResolvedValue({
      service: "AgroDrone API",
      version: "0.2.0",
      environment: "test",
      phase: "Phase 2 — Core Operations, Auth & Geospatial",
      database_connected: true,
      database_dialect: "sqlite",
      database_latency_ms: 0.4,
      storage_backend: "local",
      ai_inference_enabled: false,
      edge_gateway_enabled: false,
      counts: {
        fields: 2,
        devices: 1,
        missions: 3,
        media_assets: 4,
        detection_jobs: 0,
        open_alerts: 0,
      },
      subsystems: [
        {
          id: "api",
          name: "FastAPI Control Plane & RBAC",
          status: "operational",
          summary: "Serving v0.2.0",
          target_phase: "Phase 2",
        },
      ],
      timestamp: "2026-11-19T14:00:00Z",
    });

    vi.spyOn(apiClient, "getCapabilities").mockResolvedValue({
      hardware_baseline: [],
      network_boundary: {
        esp32_ap_ssid: "agroDrone",
        esp32_dashboard_url: "http://192.168.4.1",
        esp32_mjpeg_stream_url: "http://192.168.4.1:81/stream",
        direct_cloud_probe_allowed: false,
        gateway_status: "not_deployed_phase_4",
        explanation: "Isolated AP",
      },
      ai_policy: {
        inference_enabled: false,
        active_model_profile: "unconfigured",
        first_working_workflow: "Phase 3 upload",
        model_honesty_notice: "Requires custom training",
        validated_target_classes: [],
        requires_custom_training_for: [],
      },
      modules: [
        {
          id: "overview",
          name: "Overview Dashboard",
          route: "/",
          phase: "Phase 2",
          status: "foundation_active",
          summary: "Live health",
        },
      ],
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <SystemProvider>
            <OverviewView />
          </SystemProvider>
        </AuthProvider>
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("FastAPI Control Plane & RBAC")).toBeInTheDocument();
    });

    expect(screen.getByText(/SSID: agroDrone/i)).toBeInTheDocument();
    expect(screen.getByText(/http:\/\/192\.168\.4\.1:81\/stream/i)).toBeInTheDocument();
    expect(screen.getByText(/Platform Overview/i)).toBeInTheDocument();
  });
});

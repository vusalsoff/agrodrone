import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/layout/auth-context";
import { SystemProvider } from "@/components/layout/system-context";
import { AuthScreen } from "@/components/modules/auth-screen";
import { ToastProvider } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
  replaceMock.mockReset();
});

function setupBaseMocks() {
  vi.spyOn(apiClient, "getMe").mockRejectedValue(new ApiClientError("Unauth", 401));
  vi.spyOn(apiClient, "getHealth").mockResolvedValue({
    status: "ok",
    service: "AgroDrone API",
    version: "0.2.0",
    environment: "test",
    database_connected: true,
    database_dialect: "sqlite",
    database_latency_ms: 0.5,
    timestamp: "2026-11-19T14:00:00Z",
  });
  vi.spyOn(apiClient, "getSystemStatus").mockResolvedValue({
    service: "AgroDrone API",
    version: "0.2.0",
    environment: "test",
    phase: "Phase 2",
    database_connected: true,
    database_dialect: "sqlite",
    database_latency_ms: 0.5,
    storage_backend: "local",
    ai_inference_enabled: false,
    edge_gateway_enabled: false,
    counts: {
      fields: 0,
      devices: 0,
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
      gateway_status: "not_deployed_phase_4",
      explanation: "",
    },
    ai_policy: {
      inference_enabled: false,
      active_model_profile: "unconfigured",
      first_working_workflow: "",
      model_honesty_notice: "",
      validated_target_classes: [],
      requires_custom_training_for: [],
    },
    modules: [],
  });
  vi.spyOn(apiClient, "getAuthPolicy").mockResolvedValue({
    status: "phase2_active",
    password_hashing: "Argon2id",
    token_scheme: "JWT + HttpOnly",
    access_token_expire_minutes: 30,
    refresh_token_expire_days: 7,
    csrf_protection: "Double-submit",
    rate_limiting: "20/60s",
    supported_roles: ["admin", "agronomist", "operator", "viewer"],
    bootstrap_required: true,
    target_phase: "Phase 2 (Active)",
  });
}

describe("AuthScreen forms and validation", () => {
  it("enforces password strength rules on registration before calling API", async () => {
    setupBaseMocks();
    const registerSpy = vi.spyOn(apiClient, "register");

    render(
      <ToastProvider>
        <AuthProvider>
          <SystemProvider>
            <AuthScreen mode="register" />
          </SystemProvider>
        </AuthProvider>
      </ToastProvider>,
    );

    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: "Ada Lovelace" } });
    fireEvent.change(screen.getByLabelText(/Work Email/i), { target: { value: "ada@agrodrone.dev" } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "weak" } });

    fireEvent.click(screen.getByRole("button", { name: /Create/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/security strength criteria/i);
    });
    expect(registerSpy).not.toHaveBeenCalled();
  });

  it("submits login credentials and redirects on success", async () => {
    setupBaseMocks();
    const loginSpy = vi.spyOn(apiClient, "login").mockResolvedValue({
      user: {
        id: "u-1",
        email: "ada@agrodrone.dev",
        full_name: "Ada Lovelace",
        role: "admin",
        is_active: true,
        created_at: "2026-11-19T14:00:00Z",
        updated_at: "2026-11-19T14:00:00Z",
      },
      access_token: "token",
      token_type: "bearer",
      expires_in_seconds: 1800,
      csrf_token: "csrf",
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <SystemProvider>
            <AuthScreen mode="login" />
          </SystemProvider>
        </AuthProvider>
      </ToastProvider>,
    );

    fireEvent.change(screen.getByLabelText(/Work Email/i), { target: { value: "ada@agrodrone.dev" } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "StrongPass#2026" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

    await waitFor(() => {
      expect(loginSpy).toHaveBeenCalledWith({
        email: "ada@agrodrone.dev",
        password: "StrongPass#2026",
      });
    });
  });
});

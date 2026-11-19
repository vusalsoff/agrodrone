import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/layout/auth-context";
import { AlertsView } from "@/components/modules/alerts-view";
import { ReportsView } from "@/components/modules/reports-view";
import { ToastProvider } from "@/components/ui/toast";
import { apiClient } from "@/lib/api-client";

vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Phase 5 AlertsView & ReportsView", () => {
  it("renders honest empty alerts and unavailable SMTP preference status", async () => {
    vi.spyOn(apiClient, "getMe").mockResolvedValue({
      id: "u1",
      email: "admin@agrodrone.io",
      full_name: "Admin",
      role: "admin",
      is_active: true,
      created_at: "2026-11-19T14:00:00Z",
      updated_at: "2026-11-19T14:00:00Z",
    });
    vi.spyOn(apiClient, "listAlertsPhase5").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(apiClient, "listAlertRules").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(apiClient, "listNotifications").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(apiClient, "getNotificationPreferences").mockResolvedValue({
      in_app_enabled: true,
      email_enabled: false,
      email_address: null,
      min_severity: "info",
      muted_trigger_types: [],
      email_available: false,
      email_status_reason: "SMTP email delivery is unavailable.",
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <AlertsView />
        </AuthProvider>
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("No operational alerts")).toBeInTheDocument();
    });
  });

  it("renders analytics empty states and report provenance limitations", async () => {
    vi.spyOn(apiClient, "listFields").mockResolvedValue({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    });
    vi.spyOn(apiClient, "listMissions").mockResolvedValue({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    });
    vi.spyOn(apiClient, "getAnalyticsOverview").mockResolvedValue({
      generated_at: "2026-11-19T17:00:00Z",
      date_from: null,
      date_to: null,
      field_id: null,
      mission_id: null,
      methodology_note: "Detection counts are not infestation severity.",
      jobs_summary: {
        total_jobs: 0,
        completed_jobs: 0,
        failed_jobs: 0,
        active_or_queued_jobs: 0,
        cancelled_jobs: 0,
        avg_inference_ms: null,
      },
      detections_summary: {
        raw_detection_items: 0,
        unique_job_class_occurrences: 0,
        human_confirmed_count: 0,
        human_rejected_count: 0,
        human_uncertain_count: 0,
        unreviewed_count: 0,
      },
      class_distribution: [],
      confidence_distribution: [],
      detection_trends: [],
      field_summaries: [],
      mission_summaries: [],
      alert_severity_distribution: [],
      open_alerts: 0,
      acknowledged_alerts: 0,
      resolved_alerts: 0,
      device_connectivity: [],
    });
    vi.spyOn(apiClient, "previewReport").mockResolvedValue({
      report_type: "field_analysis",
      title: "Field Analysis Report",
      generated_at: "2026-11-19T17:00:00Z",
      generated_by_email: "admin@agrodrone.io",
      date_from: null,
      date_to: null,
      field_id: null,
      mission_id: null,
      summary_metrics: { fields_count: 0 },
      model_provenance: [],
      human_review_status: { confirmed: 0, rejected: 0, uncertain: 0, unreviewed: 0 },
      methodological_limitations: ["Baseline YOLOv8n uses COCO general-object classes only."],
      rows: [],
    });

    render(
      <ToastProvider>
        <ReportsView />
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText("No completed detection records match the current filters."),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText("Baseline YOLOv8n uses COCO general-object classes only."),
    ).toBeInTheDocument();
  });
});

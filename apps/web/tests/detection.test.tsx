import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/layout/auth-context";
import { SystemProvider } from "@/components/layout/system-context";
import { DetectionInspector } from "@/components/modules/detection-inspector";
import { DetectionView } from "@/components/modules/detection-view";
import { ToastProvider } from "@/components/ui/toast";
import { apiClient } from "@/lib/api-client";
import type { DetectionJobDetailRead } from "@/types/api";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function mockAuthAndSystem() {
  vi.spyOn(apiClient, "getMe").mockResolvedValue({
    id: "u-1",
    email: "agro@agrodrone.dev",
    full_name: "Lead Agronomist",
    role: "agronomist",
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
    phase: "Phase 3 — AgroVision AI Engine Active",
    database_connected: true,
    database_dialect: "sqlite",
    database_latency_ms: 0.4,
    storage_backend: "local",
    ai_inference_enabled: true,
    edge_gateway_enabled: false,
    counts: {
      fields: 1,
      devices: 1,
      missions: 1,
      media_assets: 1,
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
      inference_enabled: true,
      active_model_profile: "yolov8n-coco-general",
      first_working_workflow: "",
      model_honesty_notice: "",
      validated_target_classes: [],
      requires_custom_training_for: [],
    },
    modules: [],
  });
}

const SAMPLE_JOB: DetectionJobDetailRead = {
  id: "job-1234-5678",
  owner_id: "u-1",
  field_id: null,
  mission_id: null,
  media_asset_id: "media-1",
  detection_mode: "general",
  model_id: "yolov8n-coco-general",
  status: "completed",
  progress_percent: 100,
  media_type: "image",
  model_name: "Ultralytics YOLOv8n — General Object Detection (COCO)",
  model_version: "8.0.0",
  model_checksum: "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
  dataset_scope: "MS COCO 2017 — 80 general classes",
  device_used: "cpu",
  confidence_threshold: 0.35,
  frame_sample_interval_ms: null,
  max_frames: null,
  total_frames_sampled: 1,
  video_duration_ms: null,
  annotated_storage_key: "detections/u-1/job-1234-5678/annotated.jpg",
  summary_json: {
    analysis_type: "still_image",
    total_detections: 1,
    class_counts: { cow: 1 },
    average_confidence: 0.87,
    width_px: 640,
    height_px: 480,
    review_counts: { unreviewed: 1, confirmed: 0, rejected: 0, uncertain: 0 },
  },
  inference_ms: 42,
  error_message: null,
  started_at: "2026-11-19T14:00:00Z",
  completed_at: "2026-11-19T14:00:01Z",
  created_at: "2026-11-19T14:00:00Z",
  updated_at: "2026-11-19T14:00:01Z",
  media_asset: {
    id: "media-1",
    mission_id: null,
    field_id: null,
    uploaded_by: "u-1",
    media_type: "image",
    upload_status: "uploaded",
    storage_backend: "local",
    storage_key: "media/u-1/2026/11/field.jpg",
    safe_filename: "field.jpg",
    original_filename: "field_row.jpg",
    mime_type: "image/jpeg",
    byte_size: 40960,
    sha256: "a".repeat(64),
    width_px: 640,
    height_px: 480,
    captured_at: null,
    geo_lat: null,
    geo_lng: null,
    geo_source: "none",
    notes: null,
    created_at: "2026-11-19T14:00:00Z",
    updated_at: "2026-11-19T14:00:00Z",
  },
  items: [
    {
      id: "item-1",
      job_id: "job-1234-5678",
      class_id: 19,
      label: "cow",
      confidence: 0.87,
      original_label: "cow",
      original_confidence: 0.87,
      bbox_x1: 100,
      bbox_y1: 120,
      bbox_x2: 280,
      bbox_y2: 340,
      frame_index: 0,
      timestamp_ms: null,
      annotated_frame_storage_key: "detections/u-1/job-1234-5678/annotated.jpg",
      review_status: "unreviewed",
      reviewer_id: null,
      reviewed_at: null,
      reviewer_notes: null,
      created_at: "2026-11-19T14:00:01Z",
      updated_at: "2026-11-19T14:00:01Z",
    },
  ],
};

describe("AgroVision DetectionView & DetectionInspector", () => {
  it("shows Model Not Available for specialized modes and disables running unavailable models", async () => {
    mockAuthAndSystem();
    vi.spyOn(apiClient, "listModels").mockResolvedValue([
      {
        model_id: "yolov8n-coco-general",
        name: "Ultralytics YOLOv8n — General Object Detection (COCO)",
        version: "8.0.0",
        detection_mode: "general",
        architecture: "YOLOv8 Nano",
        license_spdx: "AGPL-3.0-only",
        dataset_scope: "MS COCO 2017",
        status: "available",
        status_reason: "Verified local YOLOv8n weights",
        weights_filename: "yolov8n.pt",
        expected_sha256: "f59b",
        actual_sha256: "f59b",
        supported_classes: ["person", "cow"],
        total_class_count: 80,
        default_confidence: 0.35,
        is_specialized_agricultural: false,
        honesty_disclaimer: "General-purpose detector only.",
        evaluation: null,
        requirements_for_activation: [],
      },
      {
        model_id: "agrovision-wildlife-v1",
        name: "AgroVision Field Wildlife Detector",
        version: "unreleased",
        detection_mode: "wildlife",
        architecture: "YOLO",
        license_spdx: "UNRELEASED",
        dataset_scope: "None",
        status: "not_available",
        status_reason: "Model Not Available — no trained snake/hedgehog weights registered.",
        weights_filename: "agrovision_wildlife_v1.pt",
        expected_sha256: null,
        actual_sha256: null,
        supported_classes: ["snake", "hedgehog"],
        total_class_count: 2,
        default_confidence: 0.45,
        is_specialized_agricultural: true,
        honesty_disclaimer: "Not released",
        evaluation: null,
        requirements_for_activation: ["Register labeled dataset"],
      },
    ]);
    vi.spyOn(apiClient, "listMedia").mockResolvedValue({
      items: [SAMPLE_JOB.media_asset!],
      total: 1,
      limit: 100,
      offset: 0,
    });

    render(
      <ToastProvider>
        <AuthProvider>
          <SystemProvider>
            <DetectionView />
          </SystemProvider>
        </AuthProvider>
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("AgroVision Field Wildlife Detector")).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Model Not Available/i).length).toBeGreaterThanOrEqual(1);

    const runBtn = screen.getByRole("button", { name: /Run AI Analysis/i });
    expect(runBtn).not.toBeDisabled();

    // Selecting the unavailable wildlife model disables the Run AI Analysis button
    fireEvent.click(screen.getByText("AgroVision Field Wildlife Detector"));
    await waitFor(() => {
      expect(runBtn).toBeDisabled();
    });
  });

  it("renders DetectionInspector and submits human review while preserving machine output", async () => {
    mockAuthAndSystem();
    const reviewSpy = vi.spyOn(apiClient, "reviewDetectionItem").mockResolvedValue({
      ...SAMPLE_JOB.items[0],
      review_status: "confirmed",
      reviewer_notes: "Verified cow",
    });
    const getJobSpy = vi.spyOn(apiClient, "getDetectionJob").mockResolvedValue({
      ...SAMPLE_JOB,
      items: [{ ...SAMPLE_JOB.items[0], review_status: "confirmed", reviewer_notes: "Verified cow" }],
    });
    const onUpdate = vi.fn();

    render(
      <ToastProvider>
        <AuthProvider>
          <DetectionInspector job={SAMPLE_JOB} onJobUpdated={onUpdate} />
        </AuthProvider>
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Human Verification · cow")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Reviewer Notes/i), {
      target: { value: "Verified cow" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Confirm$/i }));

    await waitFor(() => {
      expect(reviewSpy).toHaveBeenCalledWith("item-1", {
        review_status: "confirmed",
        reviewer_notes: "Verified cow",
        corrected_label: null,
      });
      expect(getJobSpy).toHaveBeenCalledWith("job-1234-5678");
      expect(onUpdate).toHaveBeenCalled();
    });
  });
});

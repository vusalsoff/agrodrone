"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Film,
  History,
  Image as ImageIcon,
  Loader2,
  Play,
  RefreshCw,
  ScanEye,
  ShieldAlert,
  UploadCloud,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { DetectionInspector } from "@/components/modules/detection-inspector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldLabel, FormError, Input, Select } from "@/components/ui/form-controls";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import {
  apiClient,
  ApiClientError,
  getMediaContentUrl,
  uploadMediaWithProgress,
} from "@/lib/api-client";
import type {
  DetectionJobDetailRead,
  MediaAssetRead,
  ModelRegistryItem,
} from "@/types/api";

export function DetectionView() {
  const { canOperate } = useAuth();
  const { refresh: refreshSystem } = useSystemState();
  const { notify } = useToast();

  const [models, setModels] = React.useState<ModelRegistryItem[]>([]);
  const [mediaList, setMediaList] = React.useState<MediaAssetRead[]>([]);
  const [loadingInit, setLoadingInit] = React.useState(true);
  const [initError, setInitError] = React.useState<string | null>(null);

  // Selection & Parameters
  const [selectedMediaId, setSelectedMediaId] = React.useState("");
  const [selectedModelId, setSelectedModelId] = React.useState("yolov8n-coco-general");
  const [confidence, setConfidence] = React.useState(0.35);
  const [sampleIntervalMs, setSampleIntervalMs] = React.useState(1000);
  const [maxFrames, setMaxFrames] = React.useState(20);

  // Upload state
  const [uploading, setUploading] = React.useState(false);
  const [uploadPercent, setUploadPercent] = React.useState(0);

  // Active Job state
  const [activeJob, setActiveJob] = React.useState<DetectionJobDetailRead | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [jobError, setJobError] = React.useState<string | null>(null);

  const loadWorkspace = React.useCallback(async () => {
    setLoadingInit(true);
    setInitError(null);
    try {
      const [modelsRes, mediaRes] = await Promise.all([
        apiClient.listModels(),
        apiClient.listMedia({ limit: 100 }),
      ]);
      setModels(modelsRes);
      setMediaList(mediaRes.items);
      if (mediaRes.items.length > 0 && !selectedMediaId) {
        setSelectedMediaId(mediaRes.items[0].id);
      }
      const firstAvail = modelsRes.find((m) => m.status === "available");
      if (firstAvail) {
        setSelectedModelId(firstAvail.model_id);
        setConfidence(firstAvail.default_confidence);
      }
    } catch (err) {
      setInitError(
        err instanceof ApiClientError ? err.message : "Failed to load AgroVision workspace.",
      );
    } finally {
      setLoadingInit(false);
    }
  }, [selectedMediaId]);

  React.useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  // Poll active job while queued or processing
  React.useEffect(() => {
    if (!activeJob || (activeJob.status !== "queued" && activeJob.status !== "processing")) {
      return;
    }
    const timer = setInterval(() => {
      void apiClient
        .getDetectionJob(activeJob.id)
        .then((updated) => {
          setActiveJob(updated);
          if (updated.status === "completed") {
            notify({
              tone: "success",
              title: "Analysis completed",
              description: `${updated.summary_json.total_detections ?? updated.items.length} detections in ${updated.inference_ms ?? 0} ms.`,
            });
            void refreshSystem();
          } else if (updated.status === "failed") {
            notify({
              tone: "error",
              title: "Analysis failed",
              description: updated.error_message ?? "Worker reported an error.",
            });
          }
        })
        .catch(() => {});
    }, 800);
    return () => clearInterval(timer);
  }, [activeJob, notify, refreshSystem]);

  const selectedMedia = React.useMemo(
    () => mediaList.find((m) => m.id === selectedMediaId) ?? null,
    [mediaList, selectedMediaId],
  );

  const selectedModel = React.useMemo(
    () => models.find((m) => m.model_id === selectedModelId) ?? null,
    [models, selectedModelId],
  );

  const handleDirectUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setUploadPercent(0);
    setJobError(null);
    try {
      const uploaded = await uploadMediaWithProgress(
        { file },
        (pct) => setUploadPercent(pct),
      );
      setMediaList((prev) => [uploaded, ...prev]);
      setSelectedMediaId(uploaded.id);
      notify({
        tone: "success",
        title: "Media uploaded",
        description: `${uploaded.original_filename} is ready for AI analysis.`,
      });
      await refreshSystem();
    } catch (err) {
      setJobError(err instanceof ApiClientError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      setUploadPercent(0);
    }
  };

  const handleStartAnalysis = async () => {
    setJobError(null);
    if (!selectedMedia) {
      setJobError("Select or upload a validated image or video first.");
      return;
    }
    if (!selectedModel || selectedModel.status !== "available") {
      setJobError(
        selectedModel?.status_reason || "Selected AI model is not available for inference.",
      );
      return;
    }

    setSubmitting(true);
    try {
      const job = await apiClient.createDetectionJob({
        media_asset_id: selectedMedia.id,
        model_id: selectedModel.model_id,
        confidence_threshold: confidence,
        frame_sample_interval_ms:
          selectedMedia.media_type === "video" ? sampleIntervalMs : undefined,
        max_frames: selectedMedia.media_type === "video" ? maxFrames : undefined,
        run_async: true,
      });
      setActiveJob(job);
      if (job.status === "completed") {
        notify({
          tone: "success",
          title: "Analysis completed",
          description: `${job.summary_json.total_detections ?? job.items.length} detections recorded.`,
        });
        void refreshSystem();
      } else {
        notify({
          tone: "info",
          title: "Analysis queued",
          description: `Running ${selectedModel.name}...`,
        });
      }
    } catch (err) {
      setJobError(
        err instanceof ApiClientError ? err.message : "Failed to start detection job.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelJob = async () => {
    if (!activeJob) return;
    try {
      const cancelled = await apiClient.cancelDetectionJob(activeJob.id);
      setActiveJob({ ...activeJob, ...cancelled });
      notify({ tone: "info", title: "Job cancelled" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Cancel failed",
        description: err instanceof ApiClientError ? err.message : "Could not cancel job.",
      });
    }
  };

  const handleRetryJob = async () => {
    if (!activeJob) return;
    try {
      const retried = await apiClient.retryDetectionJob(activeJob.id);
      setActiveJob(retried);
      notify({ tone: "info", title: "Job re-queued" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Retry failed",
        description: err instanceof ApiClientError ? err.message : "Could not retry job.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="AgroVision AI Detection"
        description="Run server-side Ultralytics YOLO object detection on uploaded field images and sampled video frames with full model provenance and human review."
        phaseBadge="Phase 3 · AgroVision Engine Active"
        phaseTone="emerald"
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link href="/history">
              <History className="h-3.5 w-3.5" />
              <span>Detection History</span>
            </Link>
          </Button>
        }
      />

      {initError && <FormError message={initError} />}

      {/* Configuration & Model Selection Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Media Selection & Parameters */}
        <Panel className="lg:col-span-5">
          <PanelHeader>
            <div>
              <PanelTitle>1. Select or Upload Media</PanelTitle>
              <PanelDescription>
                Analyze images or sampled video frames captured from ESP32-CAM or field uploads.
              </PanelDescription>
            </div>
            {canOperate && (
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20">
                <UploadCloud className="h-3.5 w-3.5" />
                <span>{uploading ? `${uploadPercent}%` : "Upload"}</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime"
                  onChange={(e) => void handleDirectUpload(e)}
                  disabled={uploading}
                  className="sr-only"
                />
              </label>
            )}
          </PanelHeader>
          <PanelBody className="space-y-4">
            {loadingInit ? (
              <Skeleton className="h-36 w-full" />
            ) : (
              <>
                <div>
                  <FieldLabel htmlFor="det-media">Uploaded Media Asset</FieldLabel>
                  <Select
                    id="det-media"
                    value={selectedMediaId}
                    onChange={(e) => setSelectedMediaId(e.target.value)}
                  >
                    <option value="">Select uploaded image or video...</option>
                    {mediaList.map((m) => (
                      <option key={m.id} value={m.id}>
                        [{m.media_type.toUpperCase()}] {m.original_filename} (
                        {(m.byte_size / 1024).toFixed(0)} KB)
                      </option>
                    ))}
                  </Select>
                </div>

                {selectedMedia && (
                  <div className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-[#090D0B] p-2.5">
                    <div className="h-14 w-20 shrink-0 overflow-hidden rounded-lg bg-black/50">
                      {selectedMedia.media_type === "image" ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={getMediaContentUrl(selectedMedia.id)}
                          alt={selectedMedia.original_filename}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full items-center justify-center text-emerald-400">
                          <Film className="h-5 w-5" />
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1 text-xs">
                      <p className="truncate font-medium text-zinc-100">
                        {selectedMedia.original_filename}
                      </p>
                      <p className="font-mono text-[10px] text-zinc-400">
                        {selectedMedia.mime_type} ·{" "}
                        {selectedMedia.width_px && selectedMedia.height_px
                          ? `${selectedMedia.width_px}×${selectedMedia.height_px}`
                          : "Video stream"}
                      </p>
                    </div>
                    <Badge tone={selectedMedia.media_type === "image" ? "emerald" : "amber"}>
                      {selectedMedia.media_type}
                    </Badge>
                  </div>
                )}

                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <FieldLabel htmlFor="det-conf">Confidence Threshold</FieldLabel>
                    <span className="font-mono text-xs text-emerald-300 tabular-nums">
                      {Math.round(confidence * 100)}% ({confidence.toFixed(2)})
                    </span>
                  </div>
                  <input
                    id="det-conf"
                    type="range"
                    min={0.05}
                    max={0.95}
                    step={0.05}
                    value={confidence}
                    onChange={(e) => setConfidence(Number(e.target.value))}
                    className="h-1.5 w-full cursor-pointer accent-emerald-400"
                  />
                </div>

                {selectedMedia?.media_type === "video" && (
                  <div className="grid grid-cols-2 gap-3 rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3">
                    <div>
                      <FieldLabel htmlFor="vid-interval">Sample Interval (ms)</FieldLabel>
                      <Input
                        id="vid-interval"
                        type="number"
                        min={200}
                        max={10000}
                        step={100}
                        value={sampleIntervalMs}
                        onChange={(e) => setSampleIntervalMs(Number(e.target.value))}
                      />
                    </div>
                    <div>
                      <FieldLabel htmlFor="vid-maxframes">Max Sampled Frames</FieldLabel>
                      <Input
                        id="vid-maxframes"
                        type="number"
                        min={1}
                        max={120}
                        value={maxFrames}
                        onChange={(e) => setMaxFrames(Number(e.target.value))}
                      />
                    </div>
                    <p className="col-span-2 text-[11px] text-amber-200/80">
                      Video jobs analyze sampled frames at the configured interval (not every raw frame).
                    </p>
                  </div>
                )}

                <FormError message={jobError} />

                {canOperate ? (
                  <Button
                    type="button"
                    variant="primary"
                    size="lg"
                    className="w-full"
                    disabled={
                      submitting ||
                      !selectedMedia ||
                      !selectedModel ||
                      selectedModel.status !== "available"
                    }
                    onClick={() => void handleStartAnalysis()}
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Starting Analysis...</span>
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4" />
                        <span>Run AI Analysis</span>
                      </>
                    )}
                  </Button>
                ) : (
                  <p className="text-xs text-zinc-500">
                    Viewer accounts have read-only access and cannot launch AI jobs.
                  </p>
                )}
              </>
            )}
          </PanelBody>
        </Panel>

        {/* Right: Modular Model Registry & Agricultural Modes */}
        <Panel className="lg:col-span-7">
          <PanelHeader>
            <div>
              <PanelTitle>2. Select Detection Mode & Verified Model</PanelTitle>
              <PanelDescription>
                Specialized wildlife, pest, and crop-disease models display &ldquo;Model Not Available&rdquo; until trained weights & evaluation metrics are registered.
              </PanelDescription>
            </div>
            <ScanEye className="h-4 w-4 text-emerald-400" />
          </PanelHeader>
          <PanelBody className="space-y-3">
            {loadingInit ? (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : (
              models.map((model) => {
                const isSelected = model.model_id === selectedModelId;
                const isAvailable = model.status === "available";
                return (
                  <button
                    key={model.model_id}
                    type="button"
                    onClick={() => {
                      setSelectedModelId(model.model_id);
                      setConfidence(model.default_confidence);
                    }}
                    className={`w-full rounded-xl border p-3.5 text-left transition-colors ${
                      isSelected
                        ? isAvailable
                          ? "border-emerald-500/45 bg-emerald-500/[0.08]"
                          : "border-amber-500/45 bg-amber-500/[0.06]"
                        : "border-white/[0.07] bg-white/[0.02] hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-zinc-100">{model.name}</span>
                          <Badge tone="muted" className="font-mono uppercase">
                            {model.detection_mode}
                          </Badge>
                        </div>
                        <p className="mt-0.5 font-mono text-[10px] text-zinc-400">
                          {model.architecture} · {model.dataset_scope}
                        </p>
                      </div>
                      <Badge tone={isAvailable ? "emerald" : "amber"}>
                        {isAvailable ? (
                          <>
                            <CheckCircle2 className="h-3 w-3" />
                            <span>Available</span>
                          </>
                        ) : (
                          <>
                            <AlertTriangle className="h-3 w-3" />
                            <span>Model Not Available</span>
                          </>
                        )}
                      </Badge>
                    </div>

                    <p className="mt-2 text-xs leading-relaxed text-zinc-400">
                      {isAvailable ? model.honesty_disclaimer : model.status_reason}
                    </p>

                    {!isAvailable && model.requirements_for_activation.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {model.requirements_for_activation.slice(0, 2).map((req) => (
                          <span
                            key={req}
                            className="rounded border border-white/[0.08] bg-black/30 px-2 py-0.5 text-[10px] text-zinc-400"
                          >
                            {req}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </PanelBody>
        </Panel>
      </div>

      {/* Live Job Progress / Error / Results */}
      {activeJob && (
        <>
          {(activeJob.status === "queued" || activeJob.status === "processing") && (
            <Panel>
              <PanelBody className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
                    <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                    <span>
                      {activeJob.status === "queued"
                        ? "Queued for AgroVision worker..."
                        : `Processing ${activeJob.media_type} (${activeJob.progress_percent}%)...`}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className="h-full bg-emerald-400 transition-all duration-200"
                      style={{ width: `${Math.max(8, activeJob.progress_percent)}%` }}
                    />
                  </div>
                </div>
                {canOperate && (
                  <Button variant="outline" size="sm" onClick={() => void handleCancelJob()}>
                    <XCircle className="h-3.5 w-3.5 text-rose-400" />
                    <span>Cancel</span>
                  </Button>
                )}
              </PanelBody>
            </Panel>
          )}

          {(activeJob.status === "failed" || activeJob.status === "cancelled") && (
            <div className="flex flex-col justify-between gap-3 rounded-xl border border-rose-500/30 bg-rose-500/[0.07] p-4 sm:flex-row sm:items-center">
              <div className="flex items-start gap-3">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
                <div>
                  <p className="text-sm font-medium text-rose-200">
                    Job {activeJob.status === "cancelled" ? "Cancelled" : "Failed"}
                  </p>
                  <p className="mt-0.5 text-xs text-rose-300/85">
                    {activeJob.error_message || "Analysis did not complete."}
                  </p>
                </div>
              </div>
              {canOperate && (
                <Button variant="outline" size="sm" onClick={() => void handleRetryJob()}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>Retry Analysis</span>
                </Button>
              )}
            </div>
          )}

          {activeJob.status === "completed" && (
            <DetectionInspector job={activeJob} onJobUpdated={setActiveJob} />
          )}
        </>
      )}

      {!activeJob && !loadingInit && mediaList.length === 0 && (
        <Panel>
          <PanelBody className="topo-grid flex min-h-[180px] flex-col items-center justify-center text-center">
            <ImageIcon className="h-5 w-5 text-emerald-400" />
            <p className="mt-3 text-sm font-medium text-zinc-100">No media uploaded yet</p>
            <p className="mt-1 max-w-md text-xs text-zinc-400">
              Upload a field photograph or MP4 clip above (or via the Media Library) to execute real
              YOLOv8n inference.
            </p>
          </PanelBody>
        </Panel>
      )}
    </div>
  );
}

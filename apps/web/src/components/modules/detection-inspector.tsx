"use client";

import * as React from "react";
import {
  CheckCircle2,
  Columns2,
  Download,
  Eye,
  FileJson,
  Film,
  HelpCircle,
  Image as ImageIcon,
  MessageSquare,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldLabel, Input, Textarea } from "@/components/ui/form-controls";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import {
  apiClient,
  ApiClientError,
  getDetectionAnnotatedUrl,
  getDetectionExportUrl,
  getDetectionFrameAnnotatedUrl,
  getMediaContentUrl,
} from "@/lib/api-client";
import type {
  DetectionItemRead,
  DetectionJobDetailRead,
  ReviewStatus,
} from "@/types/api";

interface DetectionInspectorProps {
  job: DetectionJobDetailRead;
  onJobUpdated: (updated: DetectionJobDetailRead) => void;
}

type ViewMode = "annotated" | "original" | "compare";

const REVIEW_BADGE: Record<
  ReviewStatus,
  { tone: "emerald" | "rose" | "amber" | "neutral"; label: string }
> = {
  unreviewed: { tone: "neutral", label: "Unreviewed" },
  confirmed: { tone: "emerald", label: "Confirmed" },
  rejected: { tone: "rose", label: "Rejected" },
  uncertain: { tone: "amber", label: "Uncertain" },
};

export function DetectionInspector({ job, onJobUpdated }: DetectionInspectorProps) {
  const { canOperate } = useAuth();
  const { notify } = useToast();

  const [viewMode, setViewMode] = React.useState<ViewMode>("annotated");
  const [comparePercent, setComparePercent] = React.useState(50);
  const [selectedItemId, setSelectedItemId] = React.useState<string | null>(
    job.items[0]?.id ?? null,
  );
  const [selectedFrameIndex, setSelectedFrameIndex] = React.useState<number>(0);

  // Review editor state
  const [notesDraft, setNotesDraft] = React.useState("");
  const [labelDraft, setLabelDraft] = React.useState("");
  const [reviewingId, setReviewingId] = React.useState<string | null>(null);

  React.useEffect(() => {
    setSelectedItemId(job.items[0]?.id ?? null);
    setSelectedFrameIndex(0);
  }, [job.id, job.items]);

  const isVideo = job.media_type === "video";
  const sampledFrames = job.summary_json.sampled_frames ?? [];

  const visibleItems = React.useMemo(() => {
    if (!isVideo) return job.items;
    return job.items.filter((item) => item.frame_index === selectedFrameIndex);
  }, [isVideo, job.items, selectedFrameIndex]);

  const selectedItem = React.useMemo(
    () => job.items.find((item) => item.id === selectedItemId) ?? null,
    [job.items, selectedItemId],
  );

  React.useEffect(() => {
    if (selectedItem) {
      setNotesDraft(selectedItem.reviewer_notes ?? "");
      setLabelDraft(selectedItem.label);
    } else {
      setNotesDraft("");
      setLabelDraft("");
    }
  }, [selectedItem]);

  const imgWidth = job.summary_json.width_px || job.media_asset?.width_px || 640;
  const imgHeight = job.summary_json.height_px || job.media_asset?.height_px || 480;

  const annotatedSrc = isVideo
    ? getDetectionFrameAnnotatedUrl(job.id, selectedFrameIndex)
    : getDetectionAnnotatedUrl(job.id);
  const originalSrc = !isVideo && job.media_asset_id ? getMediaContentUrl(job.media_asset_id) : null;

  const handleReview = async (item: DetectionItemRead, status: ReviewStatus) => {
    setReviewingId(item.id);
    try {
      const updatedItem = await apiClient.reviewDetectionItem(item.id, {
        review_status: status,
        reviewer_notes: notesDraft.trim() || null,
        corrected_label:
          labelDraft.trim() && labelDraft.trim() !== item.label ? labelDraft.trim() : null,
      });

      const refreshed = await apiClient.getDetectionJob(job.id);
      onJobUpdated(refreshed);
      setSelectedItemId(updatedItem.id);
      notify({
        tone: "success",
        title: `Detection ${REVIEW_BADGE[status].label}`,
        description: `${updatedItem.label} (${Math.round(updatedItem.confidence * 100)}%)`,
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Review update failed",
        description: err instanceof ApiClientError ? err.message : "Unable to save review.",
      });
    } finally {
      setReviewingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Sampling Honesty Notice for Video */}
      {isVideo && job.summary_json.sampling_notice && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3 text-xs text-amber-200/90">
          <Film className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <div>
            <span className="font-semibold text-amber-100">Sampled-Frame Video Analysis: </span>
            {job.summary_json.sampling_notice}
          </div>
        </div>
      )}

      {/* Top Metadata & Export Bar */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="surface-card rounded-xl p-3">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Detections</span>
          <p className="mt-1 font-mono text-lg font-semibold text-zinc-50 tabular-nums">
            {job.summary_json.total_detections ?? job.items.length}
          </p>
        </div>
        <div className="surface-card rounded-xl p-3">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Inference Time</span>
          <p className="mt-1 font-mono text-lg font-semibold text-emerald-300 tabular-nums">
            {job.inference_ms !== null ? `${job.inference_ms} ms` : "—"}
          </p>
        </div>
        <div className="surface-card rounded-xl p-3">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Threshold</span>
          <p className="mt-1 font-mono text-lg font-semibold text-zinc-100 tabular-nums">
            {Math.round(job.confidence_threshold * 100)}%
          </p>
        </div>
        <div className="surface-card rounded-xl p-3">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Compute</span>
          <p className="mt-1 font-mono text-sm font-semibold text-zinc-200 uppercase">
            {job.device_used}
          </p>
        </div>
        <div className="surface-card rounded-xl p-3">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Resolution</span>
          <p className="mt-1 font-mono text-sm font-semibold text-zinc-200">
            {imgWidth}×{imgHeight}
          </p>
        </div>
        <div className="surface-card rounded-xl p-3">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Human Review</span>
          <p className="mt-1 font-mono text-xs text-zinc-300">
            {job.summary_json.review_counts
              ? `${job.summary_json.review_counts.confirmed} ok · ${job.summary_json.review_counts.rejected} rej`
              : `${job.items.filter((i) => i.review_status === "confirmed").length} confirmed`}
          </p>
        </div>
      </div>

      {/* Main Inspector Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Visual Viewport + Interactive Bounding Box Highlight */}
        <Panel className="lg:col-span-7">
          <PanelHeader>
            <div>
              <PanelTitle>Visual Inspection & Bounding Box Overlay</PanelTitle>
              <PanelDescription>
                Click any detection in the list to highlight its exact coordinates.
              </PanelDescription>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {!isVideo && originalSrc && (
                <>
                  <Button
                    type="button"
                    variant={viewMode === "annotated" ? "subtle" : "ghost"}
                    size="sm"
                    onClick={() => setViewMode("annotated")}
                  >
                    <Eye className="h-3.5 w-3.5" />
                    <span>Annotated</span>
                  </Button>
                  <Button
                    type="button"
                    variant={viewMode === "original" ? "subtle" : "ghost"}
                    size="sm"
                    onClick={() => setViewMode("original")}
                  >
                    <ImageIcon className="h-3.5 w-3.5" />
                    <span>Original</span>
                  </Button>
                  <Button
                    type="button"
                    variant={viewMode === "compare" ? "subtle" : "ghost"}
                    size="sm"
                    onClick={() => setViewMode("compare")}
                  >
                    <Columns2 className="h-3.5 w-3.5" />
                    <span>Compare</span>
                  </Button>
                </>
              )}
            </div>
          </PanelHeader>

          <PanelBody className="space-y-4">
            {/* Video Sampled Frame Strip */}
            {isVideo && sampledFrames.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 font-mono text-[10px] uppercase text-zinc-500">
                  Sampled Frames:
                </span>
                {sampledFrames.map((f) => (
                  <button
                    key={f.frame_index}
                    type="button"
                    onClick={() => setSelectedFrameIndex(f.frame_index)}
                    className={`rounded-md border px-2 py-1 font-mono text-[11px] transition-colors ${
                      selectedFrameIndex === f.frame_index
                        ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                        : "border-white/[0.08] bg-white/[0.02] text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    #{f.frame_index} · {f.timestamp_ms}ms ({f.detection_count})
                  </button>
                ))}
              </div>
            )}

            {/* Image / Compare Viewport with Interactive SVG Highlight Layer */}
            <div className="relative overflow-hidden rounded-xl border border-white/[0.08] bg-[#080B0A]">
              {viewMode === "compare" && originalSrc ? (
                <div className="relative select-none">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={annotatedSrc}
                    alt="Annotated YOLO detection output"
                    className="block max-h-[500px] w-full object-contain"
                  />
                  <div
                    className="absolute inset-0 overflow-hidden"
                    style={{ clipPath: `inset(0 ${100 - comparePercent}% 0 0)` }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={originalSrc}
                      alt="Original uploaded field image"
                      className="block max-h-[500px] w-full object-contain"
                    />
                  </div>
                  <div
                    className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]"
                    style={{ left: `${comparePercent}%` }}
                  />
                  <span className="pointer-events-none absolute top-2.5 left-2.5 rounded bg-black/70 px-2 py-0.5 font-mono text-[10px] text-zinc-200">
                    ORIGINAL
                  </span>
                  <span className="pointer-events-none absolute top-2.5 right-2.5 rounded bg-emerald-950/80 px-2 py-0.5 font-mono text-[10px] text-emerald-300">
                    ANNOTATED
                  </span>
                </div>
              ) : (
                <div className="relative">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={viewMode === "original" && originalSrc ? originalSrc : annotatedSrc}
                    alt={
                      viewMode === "original"
                        ? "Original uploaded field image"
                        : "Annotated YOLO detection output"
                    }
                    className="block max-h-[500px] w-full object-contain"
                  />

                  {/* Interactive SVG overlay scaled to exact image pixel coordinates */}
                  <svg
                    viewBox={`0 0 ${imgWidth} ${imgHeight}`}
                    preserveAspectRatio="xMidYMid meet"
                    className="pointer-events-none absolute inset-0 h-full w-full"
                    aria-hidden="true"
                  >
                    {visibleItems.map((item) => {
                      const isSelected = item.id === selectedItemId;
                      if (!isSelected) return null;
                      const w = Math.max(1, item.bbox_x2 - item.bbox_x1);
                      const h = Math.max(1, item.bbox_y2 - item.bbox_y1);
                      return (
                        <g key={item.id}>
                          <rect
                            x={item.bbox_x1}
                            y={item.bbox_y1}
                            width={w}
                            height={h}
                            fill="rgba(16, 185, 129, 0.16)"
                            stroke="#F59E0B"
                            strokeWidth={Math.max(3, Math.round(imgWidth / 220))}
                          />
                        </g>
                      );
                    })}
                  </svg>
                </div>
              )}
            </div>

            {viewMode === "compare" && originalSrc && (
              <div className="flex items-center gap-3 px-1">
                <span className="font-mono text-[10px] text-zinc-400">Split</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={comparePercent}
                  onChange={(e) => setComparePercent(Number(e.target.value))}
                  aria-label="Before and after comparison split"
                  className="h-1.5 flex-1 cursor-pointer accent-emerald-400"
                />
                <span className="font-mono text-[10px] text-emerald-300 tabular-nums">
                  {comparePercent}%
                </span>
              </div>
            )}

            {/* Provenance + Export Actions */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-3">
              <div className="font-mono text-[10px] text-zinc-500">
                <div>Model: {job.model_name} ({job.model_version})</div>
                {job.model_checksum && (
                  <div>SHA-256: {job.model_checksum.slice(0, 20)}...</div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" asChild>
                  <a
                    href={getDetectionAnnotatedUrl(job.id, true)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Download className="h-3.5 w-3.5" />
                    <span>Annotated JPG</span>
                  </a>
                </Button>
                <Button variant="subtle" size="sm" asChild>
                  <a href={getDetectionExportUrl(job.id)} target="_blank" rel="noreferrer">
                    <FileJson className="h-3.5 w-3.5" />
                    <span>Export JSON</span>
                  </a>
                </Button>
              </div>
            </div>
          </PanelBody>
        </Panel>

        {/* Right: Detection List & Human-in-the-Loop Review */}
        <div className="space-y-4 lg:col-span-5">
          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>
                  Detected Objects ({visibleItems.length}
                  {isVideo ? ` in Frame #${selectedFrameIndex}` : ""})
                </PanelTitle>
                <PanelDescription>
                  Machine predictions preserved independently of human verification.
                </PanelDescription>
              </div>
            </PanelHeader>
            <PanelBody className="space-y-2">
              {visibleItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-white/[0.10] p-6 text-center text-xs text-zinc-400">
                  No objects exceeded the {Math.round(job.confidence_threshold * 100)}% confidence
                  threshold{isVideo ? ` in frame #${selectedFrameIndex}` : ""}.
                </div>
              ) : (
                <div className="max-h-[260px] space-y-1.5 overflow-y-auto pr-1">
                  {visibleItems.map((item) => {
                    const isSelected = item.id === selectedItemId;
                    const revBadge = REVIEW_BADGE[item.review_status];
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setSelectedItemId(item.id)}
                        className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-left text-xs transition-colors ${
                          isSelected
                            ? "border-emerald-500/40 bg-emerald-500/[0.10]"
                            : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]"
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-zinc-100">{item.label}</span>
                            <span className="font-mono text-[11px] text-emerald-300 tabular-nums">
                              {(item.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="mt-0.5 font-mono text-[10px] text-zinc-500">
                            bbox [{Math.round(item.bbox_x1)}, {Math.round(item.bbox_y1)},{" "}
                            {Math.round(item.bbox_x2)}, {Math.round(item.bbox_y2)}]
                            {item.timestamp_ms !== null ? ` · ${item.timestamp_ms}ms` : ""}
                          </div>
                        </div>
                        <Badge tone={revBadge.tone}>{revBadge.label}</Badge>
                      </button>
                    );
                  })}
                </div>
              )}
            </PanelBody>
          </Panel>

          {/* Human Review Panel */}
          {selectedItem && (
            <Panel>
              <PanelHeader>
                <div>
                  <PanelTitle>Human Verification · {selectedItem.label}</PanelTitle>
                  <PanelDescription>
                    Original model output:{" "}
                    <code className="font-mono text-zinc-300">
                      {selectedItem.original_label ?? selectedItem.label} (
                      {(
                        (selectedItem.original_confidence ?? selectedItem.confidence) * 100
                      ).toFixed(1)}
                      %)
                    </code>
                  </PanelDescription>
                </div>
                <Badge tone={REVIEW_BADGE[selectedItem.review_status].tone}>
                  {REVIEW_BADGE[selectedItem.review_status].label}
                </Badge>
              </PanelHeader>
              <PanelBody className="space-y-3">
                {canOperate ? (
                  <>
                    <div>
                      <FieldLabel htmlFor="rev-label">Verified Label (Optional Override)</FieldLabel>
                      <Input
                        id="rev-label"
                        value={labelDraft}
                        onChange={(e) => setLabelDraft(e.target.value)}
                        placeholder={selectedItem.label}
                      />
                    </div>
                    <div>
                      <FieldLabel htmlFor="rev-notes">Reviewer Notes</FieldLabel>
                      <Textarea
                        id="rev-notes"
                        value={notesDraft}
                        onChange={(e) => setNotesDraft(e.target.value)}
                        placeholder="Agronomist verification notes, lighting context, false positive reason..."
                        className="min-h-[68px]"
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="primary"
                        size="sm"
                        disabled={reviewingId === selectedItem.id}
                        onClick={() => void handleReview(selectedItem, "confirmed")}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Confirm</span>
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={reviewingId === selectedItem.id}
                        onClick={() => void handleReview(selectedItem, "rejected")}
                      >
                        <XCircle className="h-3.5 w-3.5 text-rose-400" />
                        <span>Reject</span>
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={reviewingId === selectedItem.id}
                        onClick={() => void handleReview(selectedItem, "uncertain")}
                      >
                        <HelpCircle className="h-3.5 w-3.5 text-amber-400" />
                        <span>Uncertain</span>
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="flex items-start gap-2 text-xs text-zinc-400">
                    <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
                    <span>
                      {selectedItem.reviewer_notes
                        ? selectedItem.reviewer_notes
                        : "Viewer accounts have read-only access to detection review records."}
                    </span>
                  </div>
                )}
              </PanelBody>
            </Panel>
          )}

          {/* Dataset Scope Honesty Card */}
          <div className="flex items-start gap-2.5 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3.5 text-[11px] text-zinc-400">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <div>
              <span className="font-semibold text-zinc-200">Dataset Scope: </span>
              {job.dataset_scope}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

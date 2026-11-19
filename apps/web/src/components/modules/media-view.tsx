"use client";

import * as React from "react";
import {
  Download,
  Eye,
  Film,
  Image as ImageIcon,
  Search,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldLabel, FormError, Input, Select } from "@/components/ui/form-controls";
import { Modal } from "@/components/ui/modal";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import {
  apiClient,
  ApiClientError,
  getMediaContentUrl,
  uploadMediaWithProgress,
} from "@/lib/api-client";
import type { FieldRead, MediaAssetRead, MissionRead } from "@/types/api";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function MediaView() {
  const { canOperate } = useAuth();
  const { status: systemStatus, refresh: refreshSystem } = useSystemState();
  const { notify } = useToast();

  const [items, setItems] = React.useState<MediaAssetRead[]>([]);
  const [fields, setFields] = React.useState<FieldRead[]>([]);
  const [missions, setMissions] = React.useState<MissionRead[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Filters
  const [search, setSearch] = React.useState("");
  const [mediaTypeFilter, setMediaTypeFilter] = React.useState("");
  const [fieldFilter, setFieldFilter] = React.useState("");

  // Upload state
  const [uploadFieldId, setUploadFieldId] = React.useState("");
  const [uploadMissionId, setUploadMissionId] = React.useState("");
  const [uploadNotes, setUploadNotes] = React.useState("");
  const [uploading, setUploading] = React.useState(false);
  const [uploadPercent, setUploadPercent] = React.useState(0);
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [dragActive, setDragActive] = React.useState(false);

  // Lightbox preview modal
  const [previewItem, setPreviewItem] = React.useState<MediaAssetRead | null>(null);

  const loadData = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mRes, fRes, misRes] = await Promise.all([
        apiClient.listMedia({
          q: search.trim() || undefined,
          media_type: mediaTypeFilter || undefined,
          field_id: fieldFilter || undefined,
          limit: 100,
        }),
        apiClient.listFields({ limit: 200 }),
        apiClient.listMissions({ limit: 200 }),
      ]);
      setItems(mRes.items);
      setTotal(mRes.total);
      setFields(fRes.items);
      setMissions(misRes.items);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load media library.");
    } finally {
      setLoading(false);
    }
  }, [search, mediaTypeFilter, fieldFilter]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      void loadData();
    }, 150);
    return () => clearTimeout(timer);
  }, [loadData]);

  const handleUploadFile = async (file: File) => {
    setUploadError(null);
    setUploading(true);
    setUploadPercent(0);

    try {
      const uploaded = await uploadMediaWithProgress(
        {
          file,
          fieldId: uploadFieldId || null,
          missionId: uploadMissionId || null,
          notes: uploadNotes || null,
        },
        (pct) => setUploadPercent(pct),
      );
      setUploadNotes("");
      notify({
        tone: "success",
        title: "Media uploaded & verified",
        description: `${uploaded.original_filename} (${formatBytes(uploaded.byte_size)}) stored securely.`,
      });
      await Promise.all([loadData(), refreshSystem()]);
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? err.message
          : "Upload rejected. Verify file type, signature, and size limits.";
      setUploadError(msg);
      notify({ tone: "error", title: "Upload rejected", description: msg });
    } finally {
      setUploading(false);
      setUploadPercent(0);
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void handleUploadFile(file);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    if (!canOperate || uploading) return;
    const file = event.dataTransfer.files?.[0];
    if (file) void handleUploadFile(file);
  };

  const handleAuthorizedDownload = async (asset: MediaAssetRead) => {
    try {
      const res = await apiClient.getMediaDownloadUrl(asset.id, true);
      const targetUrl =
        res.storage_backend === "s3" ? res.url : getMediaContentUrl(asset.id, true);
      window.open(targetUrl, "_blank", "noopener,noreferrer");
    } catch (err) {
      notify({
        tone: "error",
        title: "Download unauthorized",
        description: err instanceof ApiClientError ? err.message : "Could not generate download link.",
      });
    }
  };

  const handleDelete = async (asset: MediaAssetRead) => {
    if (!window.confirm(`Permanently delete "${asset.original_filename}"?`)) return;
    try {
      await apiClient.deleteMedia(asset.id);
      if (previewItem?.id === asset.id) setPreviewItem(null);
      notify({ tone: "info", title: "Media deleted", description: asset.original_filename });
      await Promise.all([loadData(), refreshSystem()]);
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: err instanceof ApiClientError ? err.message : "Unable to delete media asset.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Media Library"
        description="Upload, validate, preview, and download field imagery and clips stored in private local or S3/MinIO buckets."
        phaseBadge={`Phase 2 · Storage: ${(systemStatus?.storage_backend ?? "local").toUpperCase()}`}
        phaseTone="emerald"
      />

      {/* Upload Workspace */}
      {canOperate && (
        <Panel>
          <PanelHeader>
            <div>
              <PanelTitle>Secure Media Upload</PanelTitle>
              <PanelDescription>
                Enforces magic-byte signature verification (JPEG, PNG, WebP, MP4, WebM, MOV), size caps, UUID storage keys, and SHA-256 digests.
              </PanelDescription>
            </div>
            <Badge tone="emerald">
              <ShieldCheck className="h-3 w-3" />
              <span>Private Access Only</span>
            </Badge>
          </PanelHeader>
          <PanelBody className="space-y-4">
            <FormError message={uploadError} />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <FieldLabel htmlFor="up-field">Link Field (Optional)</FieldLabel>
                <Select
                  id="up-field"
                  value={uploadFieldId}
                  onChange={(e) => setUploadFieldId(e.target.value)}
                >
                  <option value="">No field linked</option>
                  {fields.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name} ({f.code})
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <FieldLabel htmlFor="up-mission">Link Mission (Optional)</FieldLabel>
                <Select
                  id="up-mission"
                  value={uploadMissionId}
                  onChange={(e) => setUploadMissionId(e.target.value)}
                >
                  <option value="">No mission linked</option>
                  {missions.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.title}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <FieldLabel htmlFor="up-notes">Capture Notes (Optional)</FieldLabel>
                <Input
                  id="up-notes"
                  placeholder="e.g., ESP32-CAM OV2640 row 2 still"
                  value={uploadNotes}
                  onChange={(e) => setUploadNotes(e.target.value)}
                />
              </div>
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              className={`topo-grid flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-8 text-center transition-colors ${
                dragActive
                  ? "border-emerald-400 bg-emerald-500/[0.08]"
                  : "border-white/[0.13] bg-[#080B0A]"
              }`}
            >
              <UploadCloud className="h-6 w-6 text-emerald-400" />
              <p className="mt-2.5 text-sm font-medium text-zinc-100">
                Drop JPEG, PNG, WebP, MP4, WebM, or MOV files here
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                SVGs, HTML, and spoofed binaries are automatically rejected by magic-byte inspection.
              </p>

              <label className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-zinc-950 transition-colors hover:bg-emerald-400">
                <span>{uploading ? `Uploading ${uploadPercent}%...` : "Select File to Upload"}</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime"
                  onChange={handleFileChange}
                  disabled={uploading}
                  className="sr-only"
                />
              </label>

              {uploading && (
                <div className="mt-4 w-full max-w-sm">
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className="h-full bg-emerald-400 transition-all duration-150"
                      style={{ width: `${uploadPercent}%` }}
                    />
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-emerald-300">{uploadPercent}%</p>
                </div>
              )}
            </div>
          </PanelBody>
        </Panel>
      )}

      {/* Gallery Filter Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-zinc-500" />
          <Input
            type="search"
            placeholder="Filter by filename..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            aria-label="Search media files"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            aria-label="Filter media type"
            value={mediaTypeFilter}
            onChange={(e) => setMediaTypeFilter(e.target.value)}
            className="w-36"
          >
            <option value="">All Media</option>
            <option value="image">Images</option>
            <option value="video">Videos</option>
          </Select>
          <Select
            aria-label="Filter media by field"
            value={fieldFilter}
            onChange={(e) => setFieldFilter(e.target.value)}
            className="w-44"
          >
            <option value="">All Fields</option>
            {fields.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>
          <Badge tone="neutral" className="font-mono">
            {total} Assets
          </Badge>
        </div>
      </div>

      {error && <FormError message={error} />}

      {/* Media Gallery */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((n) => (
            <Skeleton key={n} className="h-56 w-full rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Panel>
          <PanelBody className="flex min-h-[220px] flex-col items-center justify-center text-center">
            <ImageIcon className="h-5 w-5 text-zinc-500" />
            <p className="mt-3 text-sm font-medium text-zinc-200">No media assets uploaded yet</p>
            <p className="mt-1 max-w-md text-xs text-zinc-400">
              Uploaded imagery is ready for Phase 3 server-side Ultralytics YOLO detection without re-uploading.
            </p>
          </PanelBody>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => (
            <Panel key={item.id} className="overflow-hidden">
              <div className="relative h-44 bg-[#080B0A]">
                {item.media_type === "image" ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={getMediaContentUrl(item.id)}
                    alt={item.original_filename}
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-2 text-zinc-400">
                    <Film className="h-7 w-7 text-emerald-400" />
                    <span className="font-mono text-[11px]">{item.mime_type}</span>
                  </div>
                )}
                <Badge
                  tone={item.media_type === "image" ? "emerald" : "amber"}
                  className="absolute top-2.5 left-2.5 font-mono uppercase"
                >
                  {item.media_type}
                </Badge>
              </div>
              <div className="space-y-2 p-3.5">
                <div className="truncate text-xs font-medium text-zinc-100" title={item.original_filename}>
                  {item.original_filename}
                </div>
                <div className="flex items-center justify-between font-mono text-[10px] text-zinc-500">
                  <span>{formatBytes(item.byte_size)}</span>
                  <span>
                    {item.width_px && item.height_px ? `${item.width_px}×${item.height_px}` : item.mime_type}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-1 border-t border-white/[0.06] pt-2.5">
                  <Button variant="ghost" size="sm" onClick={() => setPreviewItem(item)}>
                    <Eye className="h-3.5 w-3.5" />
                    <span>Preview</span>
                  </Button>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => void handleAuthorizedDownload(item)}
                      title="Authorized download"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                    {canOperate && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => void handleDelete(item)}
                        title="Delete media"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          ))}
        </div>
      )}

      {/* Lightbox Preview Modal */}
      <Modal
        open={Boolean(previewItem)}
        onClose={() => setPreviewItem(null)}
        title={previewItem?.original_filename ?? "Media Preview"}
        description={
          previewItem
            ? `${previewItem.mime_type} · ${formatBytes(previewItem.byte_size)} · SHA-256 ${previewItem.sha256.slice(0, 16)}...`
            : undefined
        }
        maxWidthClass="max-w-3xl"
      >
        {previewItem && (
          <div className="space-y-4">
            <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#080B0A]">
              {previewItem.media_type === "image" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={getMediaContentUrl(previewItem.id)}
                  alt={previewItem.original_filename}
                  className="max-h-[460px] w-full object-contain"
                />
              ) : (
                <video
                  src={getMediaContentUrl(previewItem.id)}
                  controls
                  className="max-h-[460px] w-full"
                />
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
              <div className="rounded-lg bg-white/[0.025] p-2.5">
                <span className="text-[10px] uppercase text-zinc-500">Storage Backend</span>
                <p className="mt-0.5 font-mono text-zinc-200 uppercase">
                  {previewItem.storage_backend}
                </p>
              </div>
              <div className="rounded-lg bg-white/[0.025] p-2.5">
                <span className="text-[10px] uppercase text-zinc-500">Resolution</span>
                <p className="mt-0.5 font-mono text-zinc-200">
                  {previewItem.width_px && previewItem.height_px
                    ? `${previewItem.width_px} × ${previewItem.height_px}`
                    : "—"}
                </p>
              </div>
              <div className="rounded-lg bg-white/[0.025] p-2.5">
                <span className="text-[10px] uppercase text-zinc-500">Safe Filename</span>
                <p className="mt-0.5 truncate font-mono text-zinc-300">
                  {previewItem.safe_filename ?? "—"}
                </p>
              </div>
              <div className="rounded-lg bg-white/[0.025] p-2.5">
                <span className="text-[10px] uppercase text-zinc-500">Uploaded</span>
                <p className="mt-0.5 font-mono text-[11px] text-zinc-300">
                  {new Date(previewItem.created_at).toLocaleString()}
                </p>
              </div>
            </div>

            {previewItem.notes && (
              <p className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-zinc-300">
                {previewItem.notes}
              </p>
            )}

            <div className="flex items-center justify-end gap-2 border-t border-white/[0.07] pt-3">
              <Button variant="primary" size="sm" onClick={() => void handleAuthorizedDownload(previewItem)}>
                <Download className="h-3.5 w-3.5" />
                <span>Authorized Download</span>
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

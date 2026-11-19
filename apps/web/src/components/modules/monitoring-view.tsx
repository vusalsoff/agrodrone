"use client";

import * as React from "react";
import {
  Activity,
  AlertTriangle,
  Camera,
  Check,
  Copy,
  KeyRound,
  Loader2,
  Play,
  Plus,
  Radio,
  RefreshCw,
  ScanEye,
  ShieldOff,
  Square,
  VideoOff,
  Wifi,
  WifiOff,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { useLanguage } from "@/components/layout/language-context";
import { PageHeader } from "@/components/layout/page-header";
import { DetectionInspector } from "@/components/modules/detection-inspector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldLabel, FormError, Input, Select } from "@/components/ui/form-controls";
import { Modal } from "@/components/ui/modal";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusDot, type DotTone } from "@/components/ui/status-dot";
import { useToast } from "@/components/ui/toast";
import {
  apiClient,
  ApiClientError,
  getGatewayLatestFrameUrl,
  getMediaContentUrl,
  uploadMediaWithProgress,
} from "@/lib/api-client";
import type {
  DetectionJobDetailRead,
  DeviceRead,
  GatewayDeploymentMode,
  GatewayDiagnosticsResponse,
  GatewayRead,
  MediaAssetRead,
} from "@/types/api";

export function MonitoringView() {
  const { canOperate } = useAuth();
  const { tr } = useLanguage();
  const { notify } = useToast();

  const [gateways, setGateways] = React.useState<GatewayRead[]>([]);
  const [devices, setDevices] = React.useState<DeviceRead[]>([]);
  const [selectedGatewayId, setSelectedGatewayId] = React.useState<string>("");
  const [diagnostics, setDiagnostics] = React.useState<GatewayDiagnosticsResponse | null>(null);
  const [snapshots, setSnapshots] = React.useState<MediaAssetRead[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Stream controls & live frame URL
  const [targetFps, setTargetFps] = React.useState(2.0);
  const [streamBusy, setStreamBusy] = React.useState(false);
  const [frameUrl, setFrameUrl] = React.useState<string | null>(null);
  const [awaitingFrame, setAwaitingFrame] = React.useState(false);
  const [capturingSnapshot, setCapturingSnapshot] = React.useState(false);
  const latestBlobRef = React.useRef<Blob | null>(null);

  // Enroll modal
  const [enrollOpen, setEnrollOpen] = React.useState(false);
  const [gwName, setGwName] = React.useState("");
  const [gwIdentifier, setGwIdentifier] = React.useState("");
  const [gwDeviceId, setGwDeviceId] = React.useState("");
  const [gwMode, setGwMode] = React.useState<GatewayDeploymentMode>("local_dev");
  const [enrollError, setEnrollError] = React.useState<string | null>(null);
  const [enrolling, setEnrolling] = React.useState(false);

  // One-time credential reveal modal
  const [issuedToken, setIssuedToken] = React.useState<string | null>(null);
  const [copiedToken, setCopiedToken] = React.useState(false);

  // Snapshot AI analysis state
  const [analyzingId, setAnalyzingId] = React.useState<string | null>(null);
  const [analyzedJob, setAnalyzedJob] = React.useState<DetectionJobDetailRead | null>(null);

  // 1-click Local Wi-Fi Direct ESP32-CAM viewer (http://192.168.4.1:81/stream)
  const [localDirectActive, setLocalDirectActive] = React.useState(false);
  const [localDirectUrl, setLocalDirectUrl] = React.useState("http://192.168.4.1:81/stream");
  const [localDirectError, setLocalDirectError] = React.useState<string | null>(null);
  const [localModelId, setLocalModelId] = React.useState<string>("plant-disease-yolov8");
  const [localCapturing, setLocalCapturing] = React.useState(false);
  const [autoAnalyze, setAutoAnalyze] = React.useState(false);
  const [autoIntervalSec, setAutoIntervalSec] = React.useState<number>(5);
  const [phoneCapturing, setPhoneCapturing] = React.useState(false);
  const phoneCameraInputRef = React.useRef<HTMLInputElement | null>(null);
  const [monitorTab, setMonitorTab] = React.useState<"local" | "gateway">("local");

  const loadGatewaysAndDevices = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [gwRes, devRes] = await Promise.all([
        apiClient.listGateways(50, 0),
        apiClient.listDevices({ limit: 100 }),
      ]);
      setGateways(gwRes.items);
      setDevices(devRes.items);
      if (gwRes.items.length > 0 && !selectedGatewayId) {
        setSelectedGatewayId(gwRes.items[0].id);
      }
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load gateways.");
    } finally {
      setLoading(false);
    }
  }, [selectedGatewayId]);

  React.useEffect(() => {
    void loadGatewaysAndDevices();
  }, [loadGatewaysAndDevices]);

  const refreshSelectedGateway = React.useCallback(async (gwId: string) => {
    if (!gwId) {
      setDiagnostics(null);
      setSnapshots([]);
      return;
    }
    try {
      const [diag, snapRes] = await Promise.all([
        apiClient.getGatewayDiagnostics(gwId),
        apiClient.listGatewaySnapshots(gwId, 20, 0),
      ]);
      setDiagnostics(diag);
      setSnapshots(snapRes.items);
      setGateways((prev) => prev.map((g) => (g.id === diag.gateway.id ? diag.gateway : g)));
    } catch {
      // Handled gracefully
    }
  }, []);

  React.useEffect(() => {
    if (!selectedGatewayId) return;
    void refreshSelectedGateway(selectedGatewayId);
    const interval = setInterval(() => {
      void refreshSelectedGateway(selectedGatewayId);
    }, 4000);
    return () => clearInterval(interval);
  }, [selectedGatewayId, refreshSelectedGateway]);

  const activeSession = diagnostics?.active_session ?? null;
  const selectedGateway = diagnostics?.gateway ?? gateways.find((g) => g.id === selectedGatewayId) ?? null;

  React.useEffect(() => {
    if (selectedGateway?.is_live) {
      setMonitorTab("gateway");
    }
  }, [selectedGateway?.is_live]);

  // Bounded live frame polling when an authorized StreamSession is active
  React.useEffect(() => {
    if (!selectedGatewayId || !activeSession || activeSession.status !== "active") {
      setAwaitingFrame(false);
      setFrameUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      latestBlobRef.current = null;
      return;
    }

    let cancelled = false;
    const pollMs = Math.max(250, Math.round(1000 / Math.max(0.5, activeSession.target_fps)));

    const fetchFrame = async () => {
      try {
        const res = await fetch(getGatewayLatestFrameUrl(selectedGatewayId), {
          credentials: "include",
          cache: "no-store",
        });
        if (cancelled) return;
        if (res.status === 204) {
          setAwaitingFrame(true);
          return;
        }
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        latestBlobRef.current = blob;
        const nextUrl = URL.createObjectURL(blob);
        setAwaitingFrame(false);
        setFrameUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return nextUrl;
        });
      } catch {
        // Transient network hiccup; next poll recovers
      }
    };

    void fetchFrame();
    const timer = setInterval(() => void fetchFrame(), pollMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedGatewayId, activeSession]);

  // Poll analyzed snapshot DetectionJob if queued/processing
  React.useEffect(() => {
    if (!analyzedJob || (analyzedJob.status !== "queued" && analyzedJob.status !== "processing")) {
      return;
    }
    const timer = setInterval(() => {
      void apiClient
        .getDetectionJob(analyzedJob.id)
        .then((updated) => {
          setAnalyzedJob(updated);
          if (updated.status === "completed") {
            notify({
              tone: "success",
              title: "Snapshot analysis complete",
              description: `${updated.summary_json.total_detections ?? updated.items.length} objects detected.`,
            });
          }
        })
        .catch(() => {});
    }, 800);
    return () => clearInterval(timer);
  }, [analyzedJob, notify]);

  const handleEnroll = async (event: React.FormEvent) => {
    event.preventDefault();
    setEnrollError(null);
    if (gwName.trim().length < 2) {
      setEnrollError("Gateway name must be at least 2 characters.");
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(gwIdentifier.trim())) {
      setEnrollError("Identifier must start with a letter/digit and contain only A-Z, 0-9, ., _, -.");
      return;
    }

    setEnrolling(true);
    try {
      const res = await apiClient.enrollGateway({
        name: gwName.trim(),
        gateway_identifier: gwIdentifier.trim(),
        device_id: gwDeviceId || null,
        deployment_mode: gwMode,
      });
      setGateways((prev) => [res.gateway, ...prev]);
      setSelectedGatewayId(res.gateway.id);
      setEnrollOpen(false);
      setGwName("");
      setGwIdentifier("");
      setIssuedToken(res.gateway_token);
      setCopiedToken(false);
      notify({
        tone: "success",
        title: "Edge Gateway enrolled",
        description: "Save your one-time gateway token securely.",
      });
    } catch (err) {
      setEnrollError(err instanceof ApiClientError ? err.message : "Failed to enroll gateway.");
    } finally {
      setEnrolling(false);
    }
  };

  const handleRotateCredential = async () => {
    if (!selectedGateway) return;
    if (!window.confirm("Rotate this gateway's credential? The existing token will stop working immediately.")) {
      return;
    }
    try {
      const res = await apiClient.rotateGatewayCredential(selectedGateway.id);
      setIssuedToken(res.gateway_token);
      setCopiedToken(false);
      await refreshSelectedGateway(selectedGateway.id);
      notify({ tone: "success", title: "Credential rotated" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Rotation failed",
        description: err instanceof ApiClientError ? err.message : "Unable to rotate credential.",
      });
    }
  };

  const handleRevoke = async () => {
    if (!selectedGateway) return;
    if (!window.confirm(`Revoke "${selectedGateway.name}"? This immediately blocks all uploads and streams.`)) {
      return;
    }
    try {
      await apiClient.revokeGateway(selectedGateway.id);
      await refreshSelectedGateway(selectedGateway.id);
      notify({ tone: "info", title: "Gateway revoked" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Revoke failed",
        description: err instanceof ApiClientError ? err.message : "Unable to revoke gateway.",
      });
    }
  };

  const handleStartStream = async () => {
    if (!selectedGateway) return;
    setStreamBusy(true);
    try {
      await apiClient.startGatewayStream(selectedGateway.id, {
        target_fps: targetFps,
        max_frame_bytes: 524288,
        duration_seconds: 300,
      });
      await refreshSelectedGateway(selectedGateway.id);
      notify({ tone: "info", title: "Stream session authorized", description: `Target ${targetFps} FPS.` });
    } catch (err) {
      notify({
        tone: "error",
        title: "Could not start stream",
        description: err instanceof ApiClientError ? err.message : "Error starting stream.",
      });
    } finally {
      setStreamBusy(false);
    }
  };

  const handleStopStream = async () => {
    if (!selectedGateway) return;
    setStreamBusy(true);
    try {
      await apiClient.stopGatewayStream(selectedGateway.id);
      await refreshSelectedGateway(selectedGateway.id);
      notify({ tone: "info", title: "Stream stopped" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Could not stop stream",
        description: err instanceof ApiClientError ? err.message : "Error stopping stream.",
      });
    } finally {
      setStreamBusy(false);
    }
  };

  const handleCaptureSnapshot = async () => {
    if (!selectedGateway || !latestBlobRef.current) return;
    setCapturingSnapshot(true);
    try {
      const file = new File(
        [latestBlobRef.current],
        `esp32_capture_${Date.now()}.jpg`,
        { type: "image/jpeg" },
      );
      await uploadMediaWithProgress({
        file,
        notes: `[gateway:${selectedGateway.id}] Captured from Live Monitoring`,
      });
      await refreshSelectedGateway(selectedGateway.id);
      notify({ tone: "success", title: "Snapshot saved to Media Library" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Snapshot capture failed",
        description: err instanceof ApiClientError ? err.message : "Upload failed.",
      });
    } finally {
      setCapturingSnapshot(false);
    }
  };

  const handleAnalyzeSnapshot = async (mediaId: string) => {
    setAnalyzingId(mediaId);
    try {
      const job = await apiClient.analyzeGatewaySnapshot(mediaId, {
        model_id: "yolov8n-coco-general",
        confidence_threshold: 0.35,
      });
      setAnalyzedJob(job);
      notify({
        tone: job.status === "completed" ? "success" : "info",
        title: job.status === "completed" ? "Snapshot analyzed" : "Analysis queued",
        description: "Using YOLOv8n general baseline model.",
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Analysis failed",
        description: err instanceof ApiClientError ? err.message : "Could not analyze snapshot.",
      });
    } finally {
      setAnalyzingId(null);
    }
  };

  const handleLocalCaptureAnalyze = React.useCallback(async () => {
    setLocalCapturing(true);
    setLocalDirectError(null);
    try {
      const job = await apiClient.captureLocalCameraAndAnalyze({
        model_id: localModelId,
        confidence_threshold: 0.25,
      });
      let detail = await apiClient.getDetectionJob(job.id);
      setAnalyzedJob(detail);

      for (let i = 0; i < 15 && (detail.status === "queued" || detail.status === "processing"); i++) {
        await new Promise((r) => setTimeout(r, 1000));
        detail = await apiClient.getDetectionJob(job.id);
        setAnalyzedJob(detail);
      }

      notify({
        tone: detail.status === "completed" ? "success" : "info",
        title: tr("Frame Captured & Analyzed", "Kadr Çəkildi və Analiz Edildi"),
        description: detail.model_name,
      });
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? err.message
          : tr("Could not capture frame from 192.168.4.1.", "192.168.4.1 ünvanından kadr çəkilmədi.");
      setLocalDirectError(msg);
      setAutoAnalyze(false);
      notify({
        tone: "error",
        title: tr("Capture failed", "Kadr çəkilmədi"),
        description: msg,
      });
    } finally {
      setLocalCapturing(false);
    }
  }, [localModelId, notify, tr]);

  React.useEffect(() => {
    if (!autoAnalyze || monitorTab !== "local") return;
    const timer = window.setInterval(() => {
      if (!localCapturing) {
        void handleLocalCaptureAnalyze();
      }
    }, autoIntervalSec * 1000);
    return () => window.clearInterval(timer);
  }, [autoAnalyze, autoIntervalSec, localCapturing, monitorTab, handleLocalCaptureAnalyze]);

  const handlePhoneCameraCapture = async (file: File) => {
    setPhoneCapturing(true);
    setLocalDirectError(null);
    try {
      const asset = await uploadMediaWithProgress({ file, notes: "Captured from phone camera" });
      const job = await apiClient.createDetectionJob({
        media_asset_id: asset.id,
        model_id: localModelId,
        confidence_threshold: 0.25,
      });
      let detail = await apiClient.getDetectionJob(job.id);
      setAnalyzedJob(detail);

      for (let i = 0; i < 20 && (detail.status === "queued" || detail.status === "processing"); i++) {
        await new Promise((r) => setTimeout(r, 800));
        detail = await apiClient.getDetectionJob(job.id);
        setAnalyzedJob(detail);
      }

      notify({
        tone: detail.status === "completed" ? "success" : "info",
        title: tr("Photo Analyzed", "Şəkil Analiz Edildi"),
        description: detail.model_name,
      });
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? err.message
          : tr("Could not analyze phone photo.", "Telefon şəkli analiz edilmədi.");
      setLocalDirectError(msg);
      notify({
        tone: "error",
        title: tr("Analysis failed", "Analiz alınmadı"),
        description: msg,
      });
    } finally {
      setPhoneCapturing(false);
    }
  };

  const statusInfo: { tone: DotTone; badgeTone: "emerald" | "amber" | "rose" | "neutral"; label: string } = !selectedGateway
    ? { tone: "neutral", badgeTone: "neutral", label: "No Gateway Selected" }
    : selectedGateway.status === "revoked"
      ? { tone: "rose", badgeTone: "rose", label: "Revoked" }
      : !selectedGateway.is_live
        ? { tone: "amber", badgeTone: "amber", label: "Gateway Offline / Expired" }
        : !selectedGateway.camera_reachable
          ? { tone: "amber", badgeTone: "amber", label: "Camera Unreachable (192.168.4.1)" }
          : activeSession
            ? { tone: "emerald", badgeTone: "emerald", label: "Live Relay Active" }
            : { tone: "emerald", badgeTone: "emerald", label: "Gateway Online · Standby" };

  const singleWifiWarning =
    typeof selectedGateway?.diagnostics_json?.single_wifi_warning === "string"
      ? selectedGateway.diagnostics_json.single_wifi_warning
      : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={tr("Live Monitoring", "Canlı Monitorinq")}
        description={tr(
          "Watch your ESP32-CAM directly on local Wi-Fi or relay through an Edge Gateway.",
          "ESP32-CAM kamerasını birbaşa yerli Wi-Fi ilə izləyin və ya Edge Gateway üzərindən ötürün.",
        )}
        phaseBadge="ESP32-CAM · OV2640"
        phaseTone="emerald"
        actions={
          canOperate && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEnrollError(null);
                setEnrollOpen(true);
              }}
            >
              <Plus className="h-3.5 w-3.5" />
              <span>{tr("Enroll Gateway", "Gateway Əlavə Et")}</span>
            </Button>
          )
        }
      />

      {error && <FormError message={error} />}

      {/* Clean 2-Mode Switcher */}
      <div className="inline-flex rounded-xl border border-white/[0.08] bg-[#0C110F] p-1">
        <button
          type="button"
          onClick={() => setMonitorTab("local")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition ${
            monitorTab === "local"
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
              : "text-zinc-400 hover:text-zinc-200 border border-transparent"
          }`}
        >
          <Radio className="h-3.5 w-3.5" />
          <span>{tr("Local Camera (192.168.4.1)", "Yerli Kamera (192.168.4.1)")}</span>
        </button>
        <button
          type="button"
          onClick={() => setMonitorTab("gateway")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition ${
            monitorTab === "gateway"
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
              : "text-zinc-400 hover:text-zinc-200 border border-transparent"
          }`}
        >
          <StatusDot tone={selectedGateway?.is_live ? "emerald" : "neutral"} pulse={Boolean(selectedGateway?.is_live)} />
          <span>{tr("Cloud Gateway Relay", "Bulud Gateway Ötürməsi")}</span>
        </button>
      </div>

      {monitorTab === "local" ? (
        <div className="space-y-4">
          <Panel>
            <PanelHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <PanelTitle className="flex items-center gap-2">
                  <Radio className="h-4 w-4 text-emerald-400" />
                  {tr("ESP32-CAM Live Stream (agroDrone Wi-Fi)", "ESP32-CAM Canlı Yayım (agroDrone Wi-Fi)")}
                </PanelTitle>
                <PanelDescription>
                  {tr(
                    "Connect Windows to agroDrone Wi-Fi and click Watch Local Camera.",
                    "Windows-u agroDrone Wi-Fi şəbəkəsinə qoşun və Yerli Kameranı İzlə düyməsinə basın.",
                  )}
                </PanelDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  aria-label={tr("Local analysis model", "Yerli analiz modeli")}
                  value={localModelId}
                  onChange={(e) => setLocalModelId(e.target.value)}
                  className="h-8 w-auto min-w-[190px] text-xs"
                >
                  <option value="plant-disease-yolov8">
                    {tr("Plant Disease (15 classes)", "Bitki Xəstəlikləri (15 sinif)")}
                  </option>
                  <option value="yolov8n-coco-general">
                    {tr("General Objects & Animals (YOLOv8n)", "Ümumi Obyekt və Heyvanlar (YOLOv8n)")}
                  </option>
                </Select>
                {canOperate && (
                  <>
                    <input
                      ref={phoneCameraInputRef}
                      type="file"
                      accept="image/*"
                      capture="environment"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        e.target.value = "";
                        if (file) {
                          void handlePhoneCameraCapture(file);
                        }
                      }}
                    />
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={phoneCapturing}
                      onClick={() => phoneCameraInputRef.current?.click()}
                    >
                      {phoneCapturing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Camera className="h-3.5 w-3.5" />
                      )}
                      <span>
                        {phoneCapturing
                          ? tr("Uploading...", "Yüklənir...")
                          : tr("Phone Camera", "Telefon Kamerası")}
                      </span>
                    </Button>
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={localCapturing}
                      onClick={() => void handleLocalCaptureAnalyze()}
                    >
                      {localCapturing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ScanEye className="h-3.5 w-3.5" />
                      )}
                      <span>
                        {localCapturing
                          ? tr("Analyzing...", "Analiz edilir...")
                          : tr("Capture & Analyze", "Çək və Analiz Et")}
                      </span>
                    </Button>
                    <div className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-[#0B0F0D] px-2 py-1">
                      <button
                        type="button"
                        onClick={() => setAutoAnalyze((prev) => !prev)}
                        className={`rounded px-2 py-0.5 text-[11px] font-medium transition ${
                          autoAnalyze
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "text-zinc-400 hover:text-zinc-200"
                        }`}
                      >
                        {autoAnalyze ? tr("Auto: ON", "Avto: AÇIQ") : tr("Auto: OFF", "Avto: BAĞLI")}
                      </button>
                      <select
                        aria-label={tr("Auto analyze interval", "Avto analiz intervalı")}
                        value={autoIntervalSec}
                        onChange={(e) => setAutoIntervalSec(Number(e.target.value))}
                        className="bg-transparent text-[11px] text-zinc-300 outline-none"
                      >
                        <option value={3} className="bg-[#0B0F0D]">3s</option>
                        <option value={5} className="bg-[#0B0F0D]">5s</option>
                        <option value={10} className="bg-[#0B0F0D]">10s</option>
                      </select>
                    </div>
                  </>
                )}
                <Button
                  variant={localDirectActive ? "outline" : "primary"}
                  size="sm"
                  onClick={() => {
                    setLocalDirectError(null);
                    if (!localDirectActive) {
                      setLocalDirectUrl(`http://192.168.4.1:81/stream?t=${Date.now()}`);
                    }
                    setLocalDirectActive((prev) => !prev);
                  }}
                >
                  {localDirectActive ? <Square className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                  <span>
                    {localDirectActive
                      ? tr("Stop Local Camera", "Yerli Kameranı Dayandır")
                      : tr("Watch Local Camera (192.168.4.1)", "Yerli Kameranı İzlə (192.168.4.1)")}
                  </span>
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a href="http://192.168.4.1" target="_blank" rel="noreferrer">
                    {tr("Open 192.168.4.1", "192.168.4.1 Aç")}
                  </a>
                </Button>
              </div>
            </PanelHeader>
            <PanelBody>
              {localDirectActive ? (
                <>
                  <div className="relative flex aspect-video max-h-[540px] w-full items-center justify-center overflow-hidden rounded-xl border border-emerald-500/25 bg-[#050807]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={localDirectUrl}
                      alt="ESP32-CAM Live MJPEG Stream"
                      className="h-full w-full object-contain"
                      onError={() =>
                        setLocalDirectError(
                          tr(
                            "Could not load http://192.168.4.1:81/stream. Confirm Windows Wi-Fi is connected to 'agroDrone' and no other browser tab is holding the stream open.",
                            "http://192.168.4.1:81/stream yüklənmədi. Windows-un 'agroDrone' Wi-Fi şəbəkəsinə qoşulu olduğunu və başqa tab-ın yayımı tutmadığını yoxlayın.",
                          ),
                        )
                      }
                    />
                  </div>
                  {localDirectError ? (
                    <p className="mt-2 text-xs text-rose-300">{localDirectError}</p>
                  ) : null}
                </>
              ) : (
                <div className="topo-grid flex aspect-video max-h-[420px] w-full flex-col items-center justify-center rounded-xl border border-dashed border-white/[0.11] bg-[#080B0A] p-8 text-center">
                  <Camera className="h-8 w-8 text-emerald-400/80" />
                  <p className="mt-3 text-sm font-medium text-zinc-200">
                    {tr("Camera Preview Ready", "Kamera Önizləməsi Hazırdır")}
                  </p>
                  <p className="mt-1 max-w-md text-xs text-zinc-400">
                    {tr(
                      "Click Watch Local Camera (192.168.4.1) above to view the live feed.",
                      "Canlı görüntünü açmaq üçün yuxarıdakı Yerli Kameranı İzlə (192.168.4.1) düyməsinə klikləyin.",
                    )}
                  </p>
                </div>
              )}
            </PanelBody>
          </Panel>

          {!loading && gateways.length === 0 && (
            <div className="flex flex-col items-start justify-between gap-3 rounded-xl border border-white/[0.08] bg-[#0C110F] p-4 sm:flex-row sm:items-center">
              <div>
                <p className="text-xs font-semibold text-zinc-100">
                  {tr("Enroll a Field Edge Gateway to Begin", "Başlamaq üçün Field Edge Gateway əlavə edin")}
                </p>
                <p className="text-xs text-zinc-400">
                  {tr(
                    "Optional: enroll an Edge Gateway if you want cloud relay and snapshot history.",
                    "İstəyə bağlı: bulud ötürməsi və kadr tarixçəsi istəyirsinizsə Edge Gateway əlavə edin.",
                  )}
                </p>
              </div>
              {canOperate && (
                <Button variant="subtle" size="sm" onClick={() => setEnrollOpen(true)}>
                  <Plus className="h-3.5 w-3.5" />
                  <span>{tr("Enroll Edge Gateway", "Edge Gateway Əlavə Et")}</span>
                </Button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-6">

      {/* Gateway Selector & Credential Bar */}
      <div className="flex flex-col gap-3 rounded-xl border border-white/[0.08] bg-[#0C110F] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <div className="min-w-[240px] flex-1 sm:max-w-xs">
            <Select
              aria-label="Select enrolled Edge Gateway"
              value={selectedGatewayId}
              onChange={(e) => setSelectedGatewayId(e.target.value)}
            >
              <option value="">Select an enrolled Edge Gateway...</option>
              {gateways.map((gw) => (
                <option key={gw.id} value={gw.id}>
                  {gw.name} ({gw.gateway_identifier}) · {gw.deployment_mode}
                </option>
              ))}
            </Select>
          </div>

          <Badge tone={statusInfo.badgeTone}>
            <StatusDot tone={statusInfo.tone} pulse={statusInfo.tone === "emerald" && Boolean(activeSession)} />
            <span>{statusInfo.label}</span>
          </Badge>

          {selectedGateway && (
            <Badge tone="muted" className="font-mono">
              {selectedGateway.deployment_mode === "local_dev" ? "Mode A · Local Dev" : "Mode B · Remote Cloud"}
            </Badge>
          )}
        </div>

        {selectedGateway && canOperate && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refreshSelectedGateway(selectedGateway.id)}
              title="Refresh diagnostics"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            {selectedGateway.status !== "revoked" && (
              <>
                <Button variant="secondary" size="sm" onClick={() => void handleRotateCredential()}>
                  <KeyRound className="h-3.5 w-3.5" />
                  <span>Rotate Token</span>
                </Button>
                <Button variant="outline" size="sm" onClick={() => void handleRevoke()}>
                  <ShieldOff className="h-3.5 w-3.5 text-rose-400" />
                  <span>Revoke</span>
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Missing Internet / Single Wi-Fi Adapter Warning */}
      {(singleWifiWarning ||
        (selectedGateway?.deployment_mode === "remote_cloud" &&
          selectedGateway.internet_reachable === false)) && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-amber-500/35 bg-amber-500/[0.07] p-4 text-xs text-amber-200"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <div>
            <p className="font-semibold text-amber-100">Network Uplink Notice</p>
            <p className="mt-0.5 leading-relaxed">
              {singleWifiWarning ??
                "The gateway reported no internet uplink. A single Wi-Fi adapter cannot remain connected to 'agroDrone' (192.168.4.x) and an internet router simultaneously. Use a second adapter (USB LTE / Ethernet) or Mode A (local_dev)."}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Bounded Live Camera Viewport */}
        <Panel className="lg:col-span-8">
          <PanelHeader>
            <div>
              <PanelTitle>ESP32-CAM (OV2640) Relayed Viewport</PanelTitle>
              <PanelDescription>
                Bounded outbound JPEG relay ({activeSession ? `${activeSession.target_fps} FPS` : "idle"}). Zero fake telemetry.
              </PanelDescription>
            </div>
            {selectedGateway && selectedGateway.status !== "revoked" && canOperate && (
              <div className="flex flex-wrap items-center gap-2">
                {!activeSession ? (
                  <>
                    <Select
                      aria-label="Relay target FPS"
                      value={String(targetFps)}
                      onChange={(e) => setTargetFps(Number(e.target.value))}
                      className="h-8 w-24 text-xs"
                    >
                      <option value="1">1 FPS</option>
                      <option value="2">2 FPS</option>
                      <option value="3">3 FPS</option>
                      <option value="5">5 FPS</option>
                    </Select>
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={streamBusy}
                      onClick={() => void handleStartStream()}
                    >
                      <Play className="h-3.5 w-3.5" />
                      <span>Start Stream</span>
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={!frameUrl || capturingSnapshot}
                      onClick={() => void handleCaptureSnapshot()}
                    >
                      <Camera className="h-3.5 w-3.5" />
                      <span>{capturingSnapshot ? "Saving..." : "Capture Snapshot"}</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={streamBusy}
                      onClick={() => void handleStopStream()}
                    >
                      <Square className="h-3.5 w-3.5 text-rose-400" />
                      <span>Stop</span>
                    </Button>
                  </>
                )}
              </div>
            )}
          </PanelHeader>
          <PanelBody>
            {loading ? (
              <Skeleton className="h-[360px] w-full rounded-xl" />
            ) : !selectedGateway ? (
              <div className="topo-grid flex min-h-[340px] flex-col items-center justify-center rounded-xl border border-dashed border-white/[0.11] bg-[#080B0A] p-8 text-center">
                <Wifi className="h-6 w-6 text-emerald-400" />
                <h3 className="mt-3 text-sm font-semibold text-zinc-100">
                  Enroll a Field Edge Gateway to Begin
                </h3>
                <p className="mt-1.5 max-w-md text-xs leading-relaxed text-zinc-400">
                  The ESP32-CAM runs on isolated Wi-Fi AP <code className="font-mono">agroDrone</code> (
                  <code className="font-mono">192.168.4.1</code>). Enroll a gateway to receive a scoped
                  outbound token and bridge frames securely to AgroDrone.
                </p>
                {canOperate && (
                  <Button
                    variant="primary"
                    size="sm"
                    className="mt-4"
                    onClick={() => setEnrollOpen(true)}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Enroll Edge Gateway</span>
                  </Button>
                )}
              </div>
            ) : activeSession && frameUrl ? (
              <div className="relative overflow-hidden rounded-xl border border-emerald-500/25 bg-[#080B0A]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={frameUrl}
                  alt="Relayed ESP32-CAM live frame"
                  className="mx-auto max-h-[460px] w-full object-contain"
                />
                <div className="absolute top-3 left-3 flex items-center gap-2 rounded-full border border-emerald-500/35 bg-black/75 px-3 py-1 font-mono text-[11px] text-emerald-300 backdrop-blur-md">
                  <StatusDot tone="emerald" pulse />
                  <span>LIVE RELAY · {activeSession.target_fps} FPS · {activeSession.frames_relayed} frames</span>
                </div>
              </div>
            ) : (
              <div className="topo-grid flex min-h-[340px] flex-col items-center justify-center rounded-xl border border-dashed border-white/[0.11] bg-[#080B0A] p-8 text-center">
                {activeSession && awaitingFrame ? (
                  <>
                    <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
                    <h3 className="mt-4 text-sm font-semibold text-zinc-100">
                      Stream Authorized — Awaiting Gateway Frame
                    </h3>
                    <p className="mt-1.5 max-w-md text-xs text-zinc-400">
                      Waiting for <code className="font-mono text-zinc-200">{selectedGateway.gateway_identifier}</code> to
                      push frames from <code className="font-mono">http://192.168.4.1:81/stream</code>.
                    </p>
                  </>
                ) : (
                  <>
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-amber-500/25 bg-amber-500/10">
                      {selectedGateway.is_live ? (
                        <VideoOff className="h-5 w-5 text-emerald-400" />
                      ) : (
                        <WifiOff className="h-5 w-5 text-amber-400" />
                      )}
                    </div>
                    <h3 className="mt-4 text-sm font-semibold text-zinc-100">
                      {selectedGateway.is_live
                        ? selectedGateway.camera_reachable
                          ? tr("Gateway Connected — Stream Idle", "Gateway Qoşulub — Yayım Gözləmədədir")
                          : tr("Gateway Connected — ESP32-CAM Unreachable", "Gateway Qoşulub — ESP32-CAM Əlçatan Deyil")
                        : tr("Gateway Offline (No Recent Heartbeat)", "Gateway Oflayndır (Siqnal Yoxdur)")}
                    </h3>
                    <p className="mt-1.5 max-w-lg text-xs leading-relaxed text-zinc-400">
                      {selectedGateway.is_live
                        ? selectedGateway.camera_reachable
                          ? tr(
                              "Click Start Stream above to begin bounded live JPEG frame relay.",
                              "Canlı JPEG kadr ötürməsini başlatmaq üçün yuxarıdakı Start Stream düyməsinə basın.",
                            )
                          : tr(
                              "The gateway daemon is online, but cannot reach http://192.168.4.1:81/stream. Verify the host is associated with Wi-Fi SSID 'agroDrone'.",
                              "Gateway proqramı aktivdir, lakin http://192.168.4.1:81/stream ünvanına çata bilmir. Kompüterin 'agroDrone' Wi-Fi şəbəkəsinə qoşulu olduğunu yoxlayın.",
                            )
                        : tr(
                            "Start the agrodrone-gateway CLI on your field computer. Offline snapshots are spooled locally and uploaded automatically on reconnect.",
                            "Kompüterdə agrodrone-gateway CLI proqramını işə salın. Birbaşa Wi-Fi görüntüsü üçün Yerli Kamera (192.168.4.1) bölməsindən istifadə edə bilərsiniz.",
                          )}
                    </p>
                  </>
                )}
              </div>
            )}
          </PanelBody>
        </Panel>

        {/* Right: Honest Link Diagnostics & Network Guidance */}
        <div className="space-y-4 lg:col-span-4">
          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Gateway Link Diagnostics</PanelTitle>
                <PanelDescription>Real metrics reported by outbound heartbeat.</PanelDescription>
              </div>
              <Activity className="h-4 w-4 text-emerald-400" />
            </PanelHeader>
            <PanelBody className="space-y-2.5 text-xs">
              <div className="grid grid-cols-2 gap-2.5">
                <div className="rounded-lg bg-white/[0.025] p-2.5">
                  <span className="text-[10px] uppercase text-zinc-500">Camera Link</span>
                  <p className="mt-0.5 font-mono text-zinc-100">
                    {selectedGateway?.camera_reachable ? "Reachable" : "Unreachable"}
                  </p>
                </div>
                <div className="rounded-lg bg-white/[0.025] p-2.5">
                  <span className="text-[10px] uppercase text-zinc-500">Observed FPS</span>
                  <p className="mt-0.5 font-mono text-emerald-300">
                    {selectedGateway?.camera_fps !== null && selectedGateway?.camera_fps !== undefined
                      ? `${selectedGateway.camera_fps.toFixed(1)} fps`
                      : "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-white/[0.025] p-2.5">
                  <span className="text-[10px] uppercase text-zinc-500">Offline Spool</span>
                  <p className="mt-0.5 font-mono text-zinc-200">
                    {selectedGateway ? `${selectedGateway.queue_depth} queued` : "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-white/[0.025] p-2.5">
                  <span className="text-[10px] uppercase text-zinc-500">Dropped Frames</span>
                  <p className="mt-0.5 font-mono text-zinc-200">
                    {selectedGateway?.dropped_frames ?? 0}
                  </p>
                </div>
              </div>

              {selectedGateway && (
                <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 font-mono text-[11px] text-zinc-400">
                  <div>Cred Prefix: {selectedGateway.credential_prefix}... (v{selectedGateway.credential_version})</div>
                  <div>
                    Last Heartbeat:{" "}
                    {selectedGateway.heartbeat_age_seconds !== null
                      ? `${selectedGateway.heartbeat_age_seconds}s ago`
                      : "Never"}
                  </div>
                </div>
              )}

              {diagnostics?.network_guidance && (
                <p className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-[11px] leading-relaxed text-zinc-400">
                  {diagnostics.network_guidance}
                </p>
              )}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Telemetry Honesty</PanelTitle>
              </div>
            </PanelHeader>
            <PanelBody className="text-xs leading-relaxed text-zinc-400">
              GPS, altitude, battery percentage, and drone attitude are intentionally omitted because
              the E88 airframe and ESP32-CAM do not expose flight-controller telemetry.
            </PanelBody>
          </Panel>
        </div>
      </div>

      {/* Snapshot Gallery & "Analyze Snapshot" AI Integration */}
      <Panel>
        <PanelHeader>
          <div>
            <PanelTitle>Captured ESP32-CAM Snapshots</PanelTitle>
            <PanelDescription>
              Stored as authenticated MediaAssets. Trigger asynchronous YOLOv8n general object detection on any frame.
            </PanelDescription>
          </div>
          <Badge tone="neutral" className="font-mono">
            {snapshots.length} Snapshots
          </Badge>
        </PanelHeader>
        <PanelBody>
          {snapshots.length === 0 ? (
            <p className="text-xs text-zinc-500">
              No snapshots captured through this gateway yet. Snapshots uploaded by the gateway daemon or captured from the live viewport appear here.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {snapshots.map((snap) => (
                <div
                  key={snap.id}
                  className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#090D0B]"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={getMediaContentUrl(snap.id)}
                    alt={snap.original_filename}
                    className="h-36 w-full object-cover"
                    loading="lazy"
                  />
                  <div className="space-y-2 p-3">
                    <p className="truncate text-xs font-medium text-zinc-100">
                      {snap.original_filename}
                    </p>
                    <p className="font-mono text-[10px] text-zinc-500">
                      {(snap.byte_size / 1024).toFixed(1)} KB ·{" "}
                      {new Date(snap.created_at).toLocaleTimeString()}
                    </p>
                    {canOperate && (
                      <Button
                        variant="subtle"
                        size="sm"
                        className="w-full"
                        disabled={analyzingId === snap.id}
                        onClick={() => void handleAnalyzeSnapshot(snap.id)}
                      >
                        <ScanEye className="h-3.5 w-3.5" />
                        <span>
                          {analyzingId === snap.id ? "Starting..." : "Analyze Snapshot (YOLOv8n)"}
                        </span>
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </PanelBody>
      </Panel>
        </div>
      )}

      {/* Inline AI Analysis Result (from Local Capture or Gateway Snapshot) */}
      {analyzedJob && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-zinc-100">
              {tr("AI Analysis Result", "AI Analiz Nəticəsi")} ({analyzedJob.status})
            </h2>
            <Badge tone="emerald" className="font-mono">
              {analyzedJob.model_name}
            </Badge>
          </div>
          {analyzedJob.status === "completed" ? (
            <DetectionInspector job={analyzedJob} onJobUpdated={setAnalyzedJob} />
          ) : (
            <Panel>
              <PanelBody className="flex items-center gap-3 text-xs text-zinc-300">
                <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                <span>
                  {tr("Processing snapshot", "Kadr analiz edilir")} ({analyzedJob.progress_percent}%)...
                </span>
              </PanelBody>
            </Panel>
          )}
        </div>
      )}

      {/* Enroll Gateway Modal */}
      <Modal
        open={enrollOpen}
        onClose={() => setEnrollOpen(false)}
        title="Enroll Field Edge Gateway"
        description="Provision an outbound-authenticated companion gateway for your ESP32-CAM."
      >
        <form onSubmit={(e) => void handleEnroll(e)} className="space-y-4">
          <FormError message={enrollError} />
          <div>
            <FieldLabel htmlFor="gw-name" required>
              Gateway Name
            </FieldLabel>
            <Input
              id="gw-name"
              placeholder="e.g., Field Laptop Edge Bridge"
              value={gwName}
              onChange={(e) => setGwName(e.target.value)}
              required
            />
          </div>
          <div>
            <FieldLabel htmlFor="gw-id" required>
              Unique Gateway Identifier
            </FieldLabel>
            <Input
              id="gw-id"
              placeholder="e.g., gw-field-laptop-01"
              value={gwIdentifier}
              onChange={(e) => setGwIdentifier(e.target.value)}
              required
            />
          </div>
          <div>
            <FieldLabel htmlFor="gw-dev">Linked Camera Device (Optional)</FieldLabel>
            <Select
              id="gw-dev"
              value={gwDeviceId}
              onChange={(e) => setGwDeviceId(e.target.value)}
            >
              <option value="">None</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.device_identifier || d.hardware_model})
                </option>
              ))}
            </Select>
          </div>
          <div>
            <FieldLabel htmlFor="gw-mode">Network Deployment Mode</FieldLabel>
            <Select
              id="gw-mode"
              value={gwMode}
              onChange={(e) => setGwMode(e.target.value as GatewayDeploymentMode)}
            >
              <option value="local_dev">Mode A — Local Dev (Windows on agroDrone Wi-Fi + Local API)</option>
              <option value="remote_cloud">Mode B — Remote Cloud (Dual Adapter: agroDrone + Internet Uplink)</option>
            </Select>
          </div>
          <div className="flex justify-end gap-2 border-t border-white/[0.07] pt-4">
            <Button type="button" variant="ghost" onClick={() => setEnrollOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={enrolling}>
              {enrolling ? "Enrolling..." : "Enroll & Issue Token"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* One-Time Gateway Credential Modal */}
      <Modal
        open={Boolean(issuedToken)}
        onClose={() => setIssuedToken(null)}
        title="One-Time Gateway Credential"
        description="Copy this token now. AgroDrone stores only its SHA-256 hash and will never show it again."
      >
        {issuedToken && (
          <div className="space-y-4 text-xs">
            <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-[#080B0A] p-3">
              <code className="flex-1 break-all font-mono text-emerald-300">{issuedToken}</code>
              <Button
                type="button"
                variant="subtle"
                size="sm"
                onClick={() => {
                  void navigator.clipboard?.writeText(issuedToken);
                  setCopiedToken(true);
                }}
              >
                {copiedToken ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copiedToken ? "Copied" : "Copy"}</span>
              </Button>
            </div>

            <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
              <p className="font-semibold text-zinc-200">PowerShell Launch Command:</p>
              <pre className="mt-2 overflow-x-auto font-mono text-[11px] text-zinc-300">
{`cd apps/api
$env:AGRODRONE_API_BASE_URL = "http://127.0.0.1:8000"
$env:AGRODRONE_GATEWAY_TOKEN = "${issuedToken}"
$env:AGRODRONE_DEPLOYMENT_MODE = "${selectedGateway?.deployment_mode ?? "local_dev"}"
.\\.venv\\Scripts\\python.exe -m agrodrone_gateway.cli`}
              </pre>
            </div>

            <div className="flex justify-end">
              <Button type="button" variant="primary" size="sm" onClick={() => setIssuedToken(null)}>
                Done
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

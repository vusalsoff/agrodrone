"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
  Compass,
  Cpu,
  Database,
  HardDrive,
  Image as ImageIcon,
  ScanEye,
  Server,
  ShieldAlert,
  Sprout,
  WifiOff,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { useLanguage } from "@/components/layout/language-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusDot, type DotTone } from "@/components/ui/status-dot";
import { apiClient } from "@/lib/api-client";
import { formatLatency, formatTimestamp } from "@/lib/utils";
import type { AnalyticsOverviewResponse, SubsystemState } from "@/types/api";

function subsystemBadge(state: SubsystemState): {
  tone: "emerald" | "amber" | "rose" | "neutral";
  dot: DotTone;
  label: string;
} {
  switch (state) {
    case "operational":
      return { tone: "emerald", dot: "emerald", label: "Operational" };
    case "standby":
      return { tone: "amber", dot: "amber", label: "Standby" };
    case "isolated_local":
      return { tone: "amber", dot: "amber", label: "Isolated AP" };
    case "degraded":
      return { tone: "rose", dot: "rose", label: "Degraded" };
    default:
      return { tone: "neutral", dot: "neutral", label: "Unconfigured" };
  }
}

export function OverviewView() {
  const { user, canManageFields, canOperate } = useAuth();
  const { tr } = useLanguage();
  const { health, status, capabilities, loading, error, lastCheckedAt, refresh } = useSystemState();

  const [scopedCounts, setScopedCounts] = React.useState<{
    fields: number;
    devices: number;
    missions: number;
    media: number;
  } | null>(null);
  const [analytics, setAnalytics] = React.useState<AnalyticsOverviewResponse | null>(null);

  const loadScopedCounts = React.useCallback(async () => {
    if (!user) return;
    try {
      const [f, d, m, med, ov] = await Promise.all([
        apiClient.listFields({ limit: 1 }),
        apiClient.listDevices({ limit: 1 }),
        apiClient.listMissions({ limit: 1 }),
        apiClient.listMedia({ limit: 1 }),
        apiClient.getAnalyticsOverview().catch(() => null),
      ]);
      setScopedCounts({
        fields: f.total,
        devices: d.total,
        missions: m.total,
        media: med.total,
      });
      if (ov) setAnalytics(ov);
    } catch {
      // Fall back to system aggregate counts when scoped query fails
    }
  }, [user]);

  React.useEffect(() => {
    void loadScopedCounts();
  }, [loadScopedCounts]);

  const kpis = [
    {
      label: tr("Fields", "Sahələr"),
      value: scopedCounts?.fields ?? status?.counts.fields ?? 0,
      meta: tr("GeoJSON parcels", "GeoJSON sahələr"),
      href: "/fields",
      icon: Sprout,
    },
    {
      label: tr("Devices", "Cihazlar"),
      value: scopedCounts?.devices ?? status?.counts.devices ?? 0,
      meta: tr("Hardware inventory", "Avadanlıq siyahısı"),
      href: "/devices",
      icon: Cpu,
    },
    {
      label: tr("Missions", "Missiyalar"),
      value: scopedCounts?.missions ?? status?.counts.missions ?? 0,
      meta: tr("Manual survey logs", "Müşahidə qeydləri"),
      href: "/missions",
      icon: Compass,
    },
    {
      label: tr("Media Assets", "Media Fayllar"),
      value: scopedCounts?.media ?? status?.counts.media_assets ?? 0,
      meta: tr("Verified uploads", "Yüklənmiş görüntülər"),
      href: "/media",
      icon: ImageIcon,
    },
    {
      label: tr("AI Detection Jobs", "AI Analiz İşləri"),
      value: status?.counts.detection_jobs ?? 0,
      meta: tr("YOLOv8n jobs", "YOLOv8n analizləri"),
      href: "/detection",
      icon: ScanEye,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={tr("Platform Overview", "Platformaya Ümumi Baxış")}
        description={tr(
          "Live operational inventory, database-backed subsystem health, and hardware boundary governance.",
          "Canlı əməliyyat göstəriciləri, sistem sağlamlığı və kamera/cihaz statusu.",
        )}
        phaseBadge={tr("AgroDrone Platform · Active", "AgroDrone Platforması · Aktiv")}
        phaseTone="emerald"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {canManageFields && (
              <Button variant="primary" size="sm" asChild>
                <Link href="/fields">{tr("Manage Fields", "Sahələri İdarə Et")}</Link>
              </Button>
            )}
            {canOperate && (
              <Button variant="outline" size="sm" asChild>
                <Link href="/media">{tr("Upload Media", "Media Yüklə")}</Link>
              </Button>
            )}
            <Button
              variant="subtle"
              size="sm"
              onClick={() => {
                void refresh();
                void loadScopedCounts();
              }}
              disabled={loading}
            >
              {tr("Sync Status", "Statusu Yenilə")}
            </Button>
          </div>
        }
      />

      {error && !loading && (
        <div
          role="alert"
          className="flex flex-col justify-between gap-3 rounded-xl border border-rose-500/30 bg-rose-500/[0.07] p-4 sm:flex-row sm:items-center"
        >
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
            <div>
              <p className="text-sm font-medium text-rose-200">FastAPI Control Plane Unreachable</p>
              <p className="mt-0.5 text-xs text-rose-300/80">
                {error} Start it locally with{" "}
                <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-[11px] text-rose-200">
                  .\scripts\dev.ps1 -Action api
                </code>
                .
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            Retry Connection
          </Button>
        </div>
      )}

      {/* Honest Database-Backed Operational Counters */}
      <section aria-label="Database entity counters" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {kpis.map((kpi, idx) => {
          const Icon = kpi.icon;
          return (
            <motion.div
              key={kpi.label}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: idx * 0.03 }}
            >
              <Link
                href={kpi.href}
                className="surface-card group flex h-full flex-col justify-between rounded-xl p-4 transition-colors hover:border-emerald-500/30"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-zinc-400">{kpi.label}</span>
                  <Icon className="h-4 w-4 text-zinc-500 transition-colors group-hover:text-emerald-400" />
                </div>
                <div className="mt-4 flex items-baseline justify-between">
                  {loading ? (
                    <Skeleton className="h-7 w-12" />
                  ) : (
                    <span className="font-mono text-2xl font-semibold tracking-tight text-zinc-50 tabular-nums">
                      {error ? "—" : kpi.value}
                    </span>
                  )}
                  <ArrowUpRight className="h-3.5 w-3.5 text-zinc-600 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-emerald-400" />
                </div>
                <p className="mt-1.5 font-mono text-[10px] text-zinc-500">{kpi.meta}</p>
              </Link>
            </motion.div>
          );
        })}
      </section>

      {analytics ? (
        <Panel>
          <PanelHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <PanelTitle>{tr("Smart Analytics & Alert Summary", "Analitika və Xəbərdarlıq Xülasəsi")}</PanelTitle>
              <PanelDescription>
                {tr(
                  "Real detection and operational metrics derived from persisted database records.",
                  "Verilənlər bazasındakı real analiz və əməliyyat göstəriciləri.",
                )}
              </PanelDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" asChild>
                <Link href="/reports">{tr("Analytics & Reports", "Analitika və Hesabatlar")}</Link>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link href="/alerts">
                  {tr("Alerts", "Xəbərdarlıqlar")} ({analytics.open_alerts} {tr("open", "açıq")})
                </Link>
              </Button>
            </div>
          </PanelHeader>
          <PanelBody className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
              <p className="text-[11px] text-zinc-400">{tr("AI Jobs Completed", "Tamamlanan AI İşləri")}</p>
              <p className="mt-1 font-mono text-lg font-semibold text-zinc-100">
                {analytics.jobs_summary.completed_jobs} / {analytics.jobs_summary.total_jobs}
              </p>
            </div>
            <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
              <p className="text-[11px] text-zinc-400">{tr("Unique Job-Class Hits", "Unikal Sinif Nəticələri")}</p>
              <p className="mt-1 font-mono text-lg font-semibold text-emerald-300">
                {analytics.detections_summary.unique_job_class_occurrences}
              </p>
            </div>
            <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
              <p className="text-[11px] text-zinc-400">{tr("Human Confirmed", "İnsan Təsdiqli")}</p>
              <p className="mt-1 font-mono text-lg font-semibold text-zinc-100">
                {analytics.detections_summary.human_confirmed_count}
              </p>
            </div>
            <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
              <p className="text-[11px] text-zinc-400">{tr("Open Alerts", "Açıq Xəbərdarlıqlar")}</p>
              <p className="mt-1 font-mono text-lg font-semibold text-amber-300">
                {analytics.open_alerts}
              </p>
            </div>
          </PanelBody>
        </Panel>
      ) : null}

      {/* Quick Operations Strip */}
      <section aria-label="Quick operations" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          {
            label: tr("New Field", "Yeni Sahə"),
            detail: tr("Draw GeoJSON parcel", "Xəritədə sahə çək"),
            href: "/fields",
            icon: Sprout,
          },
          {
            label: tr("New Mission", "Yeni Missiya"),
            detail: tr("Log survey & link media", "Müşahidə və media əlavə et"),
            href: "/missions",
            icon: Compass,
          },
          {
            label: tr("AI Detection", "AI Aşkarlama"),
            detail: tr("Run YOLOv8n analysis", "YOLOv8n analizi başlat"),
            href: "/detection",
            icon: ScanEye,
          },
          {
            label: tr("Export Report", "Hesabat İxracı"),
            detail: tr("PDF, CSV & JSON debrief", "PDF, CSV və JSON hesabat"),
            href: "/reports",
            icon: HardDrive,
          },
        ].map((action) => {
          const ActionIcon = action.icon;
          return (
            <Link
              key={action.href}
              href={action.href}
              className="surface-card group flex items-center gap-3 rounded-xl px-4 py-3 transition-colors hover:border-emerald-500/35 hover:bg-emerald-500/[0.04]"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-300">
                <ActionIcon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-zinc-100 group-hover:text-emerald-200">
                  {action.label}
                </p>
                <p className="truncate text-[11px] text-zinc-500">{action.detail}</p>
              </div>
            </Link>
          );
        })}
      </section>

      {/* Main 12-column operational grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Panel className="lg:col-span-7">
          <PanelHeader>
            <div>
              <PanelTitle>{tr("Control Plane & Subsystem Health", "Sistem və Alt-Sistem Sağlamlığı")}</PanelTitle>
              <PanelDescription>
                {tr(
                  "Real-time probe of FastAPI RBAC, relational store, private media storage, AI worker, and Edge Gateway.",
                  "FastAPI, verilənlər bazası, media anbarı, AI worker və Edge Gateway-in real vaxt yoxlanışı.",
                )}
              </PanelDescription>
            </div>
            <Badge tone={health?.status === "ok" ? "emerald" : "neutral"} className="font-mono">
              {lastCheckedAt ? `Checked ${formatTimestamp(lastCheckedAt)}` : "Awaiting check"}
            </Badge>
          </PanelHeader>
          <PanelBody className="space-y-3">
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((n) => (
                  <Skeleton key={n} className="h-14 w-full rounded-lg" />
                ))}
              </div>
            ) : status?.subsystems ? (
              status.subsystems.map((sub) => {
                const badge = subsystemBadge(sub.status);
                return (
                  <div
                    key={sub.id}
                    className="flex flex-col justify-between gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3 sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <StatusDot tone={badge.dot} />
                        <span className="text-sm font-medium text-zinc-100">{sub.name}</span>
                        <span className="font-mono text-[10px] text-zinc-500">
                          {sub.target_phase}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-zinc-400">{sub.summary}</p>
                    </div>
                    <Badge tone={badge.tone} className="self-start sm:self-center">
                      {badge.label}
                    </Badge>
                  </div>
                );
              })
            ) : (
              <div className="rounded-lg border border-dashed border-white/[0.09] p-6 text-center text-xs text-zinc-400">
                Subsystem telemetry becomes visible once the FastAPI backend is reachable at{" "}
                <code className="font-mono text-zinc-300">/api/v1/system/status</code>.
              </div>
            )}

            {health && (
              <div className="mt-2 grid grid-cols-3 gap-3 border-t border-white/[0.06] pt-3">
                <div className="rounded-lg bg-white/[0.02] p-2.5">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500">
                    <Database className="h-3 w-3" />
                    <span>Dialect</span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-zinc-200 uppercase">
                    {health.database_dialect}
                  </p>
                </div>
                <div className="rounded-lg bg-white/[0.02] p-2.5">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500">
                    <Server className="h-3 w-3" />
                    <span>DB Ping</span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-emerald-300 tabular-nums">
                    {formatLatency(health.database_latency_ms)}
                  </p>
                </div>
                <div className="rounded-lg bg-white/[0.02] p-2.5">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500">
                    <HardDrive className="h-3 w-3" />
                    <span>Storage</span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-zinc-200 uppercase">
                    {status?.storage_backend ?? "—"}
                  </p>
                </div>
              </div>
            )}
          </PanelBody>
        </Panel>

        <Panel className="lg:col-span-5">
          <PanelHeader>
            <div>
              <PanelTitle>{tr("Hardware & Network Boundary", "Avadanlıq və Şəbəkə Sərhədi")}</PanelTitle>
              <PanelDescription>
                {tr(
                  "Architectural separation between field hardware AP and cloud control plane.",
                  "Sahə kamerası (AP) ilə əsas platforma arasındakı şəbəkə ayrımı.",
                )}
              </PanelDescription>
            </div>
            <Badge tone="amber">{tr("Local AP Only", "Yalnız Yerli AP")}</Badge>
          </PanelHeader>
          <PanelBody className="space-y-4">
            <div className="topo-grid space-y-2.5 rounded-xl border border-white/[0.07] bg-[#090C0B] p-4">
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/[0.06] p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-amber-200">
                    ESP32-CAM (OV2640) · Isolated AP
                  </span>
                  <WifiOff className="h-3.5 w-3.5 text-amber-400" />
                </div>
                <div className="mt-1.5 space-y-0.5 font-mono text-[11px] text-zinc-300">
                  <div>SSID: {capabilities?.network_boundary.esp32_ap_ssid ?? "agroDrone"}</div>
                  <div>UI: {capabilities?.network_boundary.esp32_dashboard_url ?? "http://192.168.4.1"}</div>
                  <div>
                    MJPEG:{" "}
                    {capabilities?.network_boundary.esp32_mjpeg_stream_url ??
                      "http://192.168.4.1:81/stream"}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3 text-[11px] text-zinc-400">
                Direct local Wi-Fi camera works at <code className="text-zinc-200">192.168.4.1</code>; cloud bridging uses <code className="text-zinc-200">services/edge-gateway</code>.
              </div>
            </div>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}

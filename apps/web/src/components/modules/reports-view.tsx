"use client";

import * as React from "react";
import {
  Activity,
  BarChart3,
  Download,
  FileSpreadsheet,
  FileText,
  Filter,
  RefreshCw,
  ShieldAlert,
  Wifi,
} from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { formatTimestamp } from "@/lib/utils";
import type {
  AnalyticsOverviewResponse,
  FieldRead,
  MissionRead,
  ReportFormat,
  ReportPreviewResponse,
  ReportType,
} from "@/types/api";

const REPORT_TYPE_OPTIONS: Array<{ value: ReportType; label: string }> = [
  { value: "field_analysis", label: "Field Analysis Report" },
  { value: "mission_summary", label: "Mission Summary Report" },
  { value: "ai_detection", label: "AI Detection Report" },
  { value: "device_activity", label: "Device & Gateway Activity Report" },
  { value: "alert_history", label: "Alert History Report" },
];

export function ReportsView() {
  const { notify } = useToast();

  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [overview, setOverview] = React.useState<AnalyticsOverviewResponse | null>(null);
  const [preview, setPreview] = React.useState<ReportPreviewResponse | null>(null);
  const [fields, setFields] = React.useState<FieldRead[]>([]);
  const [missions, setMissions] = React.useState<MissionRead[]>([]);

  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [fieldId, setFieldId] = React.useState("");
  const [missionId, setMissionId] = React.useState("");
  const [reportType, setReportType] = React.useState<ReportType>("field_analysis");
  const [exporting, setExporting] = React.useState<ReportFormat | null>(null);

  const loadMetadata = React.useCallback(async () => {
    try {
      const [fRes, mRes] = await Promise.all([
        apiClient.listFields({ limit: 200 }),
        apiClient.listMissions({ limit: 200 }),
      ]);
      setFields(fRes.items);
      setMissions(mRes.items);
    } catch {
      // ignore selector fallback
    }
  }, []);

  const loadAnalyticsAndPreview = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      field_id: fieldId || undefined,
      mission_id: missionId || undefined,
    };
    try {
      const [ov, pv] = await Promise.all([
        apiClient.getAnalyticsOverview(params),
        apiClient.previewReport({ report_type: reportType, ...params }),
      ]);
      setOverview(ov);
      setPreview(pv);
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : "Failed to load analytics & report preview.",
      );
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, fieldId, missionId, reportType]);

  React.useEffect(() => {
    void loadMetadata();
  }, [loadMetadata]);

  React.useEffect(() => {
    void loadAnalyticsAndPreview();
  }, [loadAnalyticsAndPreview]);

  const handleDownload = async (format: ReportFormat) => {
    setExporting(format);
    try {
      const url = apiClient.reportExportUrl({
        report_type: reportType,
        format,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        field_id: fieldId || undefined,
        mission_id: missionId || undefined,
      });
      const res = await fetch(url, {
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error(`Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `agrodrone-${reportType}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      notify({
        tone: "success",
        title: `Exported ${format.toUpperCase()} report`,
        description: REPORT_TYPE_OPTIONS.find((o) => o.value === reportType)?.label,
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Report export failed",
        description: err instanceof Error ? err.message : "Could not export report.",
      });
    } finally {
      setExporting(null);
    }
  };

  const maxClassCount = Math.max(
    1,
    ...(overview?.class_distribution.map((c) => c.raw_count) ?? [1]),
  );
  const maxTrendCount = Math.max(
    1,
    ...(overview?.detection_trends.map((t) => t.raw_detections) ?? [1]),
  );
  const maxBucketCount = Math.max(
    1,
    ...(overview?.confidence_distribution.map((b) => b.count) ?? [1]),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        phaseBadge="Phase 5 · Smart Analytics & Reporting"
        phaseTone="emerald"
        title="Reports & Analytics"
        description="Real database-backed analytics, deduplicated video summaries, connectivity history, and exportable PDF, CSV, and JSON reports."
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void loadAnalyticsAndPreview()}
            disabled={loading}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />

      {/* Filter Bar */}
      <Panel>
        <PanelHeader>
          <PanelTitle className="flex items-center gap-2 text-sm">
            <Filter className="h-4 w-4 text-emerald-400" />
            Scope & Date Range Filters
          </PanelTitle>
        </PanelHeader>
        <PanelBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="mb-1 block text-[11px] text-zinc-400">From Date</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-zinc-400">To Date</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-zinc-400">Field</label>
            <select
              value={fieldId}
              onChange={(e) => setFieldId(e.target.value)}
              aria-label="Filter by field"
              className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100"
            >
              <option value="">All Fields</option>
              {fields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name} ({f.code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-zinc-400">Mission</label>
            <select
              value={missionId}
              onChange={(e) => setMissionId(e.target.value)}
              aria-label="Filter by mission"
              className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100"
            >
              <option value="">All Missions</option>
              {missions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          </div>
        </PanelBody>
      </Panel>

      {error ? (
        <Panel className="border-rose-500/30">
          <PanelBody className="text-sm text-rose-300">{error}</PanelBody>
        </Panel>
      ) : null}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : null}

      {!loading && overview ? (
        <>
          {/* KPI Summary Strip */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Panel>
              <PanelBody className="p-4">
                <p className="text-xs text-zinc-400">Detection Jobs</p>
                <p className="mt-1 font-mono text-2xl font-semibold text-zinc-50">
                  {overview.jobs_summary.total_jobs}
                </p>
                <p className="mt-1 text-[11px] text-zinc-500">
                  {overview.jobs_summary.completed_jobs} completed · {overview.jobs_summary.failed_jobs} failed
                </p>
              </PanelBody>
            </Panel>
            <Panel>
              <PanelBody className="p-4">
                <p className="text-xs text-zinc-400">Unique Job-Class Occurrences</p>
                <p className="mt-1 font-mono text-2xl font-semibold text-emerald-300">
                  {overview.detections_summary.unique_job_class_occurrences}
                </p>
                <p className="mt-1 text-[11px] text-zinc-500">
                  {overview.detections_summary.raw_detection_items} raw frame/image instances
                </p>
              </PanelBody>
            </Panel>
            <Panel>
              <PanelBody className="p-4">
                <p className="text-xs text-zinc-400">Human Review Status</p>
                <p className="mt-1 font-mono text-2xl font-semibold text-zinc-50">
                  {overview.detections_summary.human_confirmed_count}
                </p>
                <p className="mt-1 text-[11px] text-zinc-500">
                  confirmed · {overview.detections_summary.unreviewed_count} unreviewed
                </p>
              </PanelBody>
            </Panel>
            <Panel>
              <PanelBody className="p-4">
                <p className="text-xs text-zinc-400">Operational Alerts</p>
                <p className="mt-1 font-mono text-2xl font-semibold text-amber-300">
                  {overview.open_alerts}
                </p>
                <p className="mt-1 text-[11px] text-zinc-500">
                  open · {overview.acknowledged_alerts} ack · {overview.resolved_alerts} resolved
                </p>
              </PanelBody>
            </Panel>
          </div>

          <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] px-4 py-3 text-xs text-amber-200/90">
            <strong>Methodology:</strong> {overview.methodology_note}
          </div>

          {/* Charts Grid */}
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel>
              <PanelHeader>
                <PanelTitle className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-emerald-400" />
                  Detected Class Distribution
                </PanelTitle>
                <PanelDescription>Raw detections vs deduplicated job-class occurrences.</PanelDescription>
              </PanelHeader>
              <PanelBody>
                {overview.class_distribution.length === 0 ? (
                  <p className="py-8 text-center text-xs text-zinc-500">
                    No completed detection records match the current filters.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {overview.class_distribution.slice(0, 8).map((item) => (
                      <div key={item.label} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-medium text-zinc-200">{item.label}</span>
                          <span className="font-mono text-[11px] text-zinc-400">
                            {item.unique_job_count} unique · {item.raw_count} raw · avg {(item.avg_confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
                          <div
                            className="h-full rounded-full bg-emerald-500"
                            style={{ width: `${Math.max(4, (item.raw_count / maxClassCount) * 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader>
                <PanelTitle className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-emerald-400" />
                  Detection Trends by Date
                </PanelTitle>
                <PanelDescription>Daily completed jobs, raw detections, and confirmed items.</PanelDescription>
              </PanelHeader>
              <PanelBody>
                {overview.detection_trends.length === 0 ? (
                  <p className="py-8 text-center text-xs text-zinc-500">
                    No time-series activity recorded in this date window.
                  </p>
                ) : (
                  <div className="space-y-2.5">
                    {overview.detection_trends.map((pt) => (
                      <div key={pt.date} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-zinc-300">{pt.date}</span>
                          <span className="font-mono text-[11px] text-zinc-400">
                            {pt.jobs_completed} jobs · {pt.raw_detections} raw · {pt.confirmed_detections} confirmed
                          </span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
                          <div
                            className="h-full rounded-full bg-sky-400"
                            style={{
                              width: `${Math.max(4, (pt.raw_detections / maxTrendCount) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader>
                <PanelTitle>Confidence Distribution</PanelTitle>
                <PanelDescription>Histogram across real YOLOv8n detection scores.</PanelDescription>
              </PanelHeader>
              <PanelBody>
                {overview.detections_summary.raw_detection_items === 0 ? (
                  <p className="py-8 text-center text-xs text-zinc-500">
                    No confidence scores available yet.
                  </p>
                ) : (
                  <div className="space-y-2.5">
                    {overview.confidence_distribution.map((bucket) => (
                      <div key={bucket.bucket_label} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-zinc-300">{bucket.bucket_label}</span>
                          <span className="font-mono text-zinc-400">{bucket.count}</span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
                          <div
                            className="h-full rounded-full bg-amber-400"
                            style={{
                              width: `${bucket.count === 0 ? 0 : Math.max(4, (bucket.count / maxBucketCount) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader>
                <PanelTitle className="flex items-center gap-2">
                  <Wifi className="h-4 w-4 text-emerald-400" />
                  Device & Gateway Connectivity History
                </PanelTitle>
                <PanelDescription>Real enrollment, heartbeat, offline TTL, and revocation events.</PanelDescription>
              </PanelHeader>
              <PanelBody>
                {overview.device_connectivity.length === 0 ? (
                  <p className="py-8 text-center text-xs text-zinc-500">
                    No ESP32-CAM edge gateways enrolled yet.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {overview.device_connectivity.map((gw) => (
                      <div
                        key={gw.gateway_id}
                        className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3 text-xs"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-zinc-100">{gw.gateway_name}</span>
                          <Badge tone={gw.current_status === "active" ? "emerald" : "neutral"}>
                            {gw.current_status}
                          </Badge>
                        </div>
                        <p className="mt-1 text-[11px] text-zinc-400">
                          {gw.total_events} events · {gw.offline_events} offline TTL breach(es) · Last heartbeat:{" "}
                          {gw.last_heartbeat_at ? formatTimestamp(gw.last_heartbeat_at) : "Never"}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </PanelBody>
            </Panel>
          </div>

          {/* Professional Report Export Workbench */}
          <Panel>
            <PanelHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <PanelTitle className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-emerald-400" />
                  Export Professional Report
                </PanelTitle>
                <PanelDescription>
                  Includes AgroDrone branding, date range, real metrics, model provenance, review status, and limitations.
                </PanelDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value as ReportType)}
                  aria-label="Report type"
                  className="rounded-lg border border-white/[0.1] bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100"
                >
                  {REPORT_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleDownload("pdf")}
                  disabled={exporting !== null}
                >
                  <Download className="h-3.5 w-3.5" />
                  {exporting === "pdf" ? "Exporting..." : "PDF"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleDownload("csv")}
                  disabled={exporting !== null}
                >
                  <FileSpreadsheet className="h-3.5 w-3.5" />
                  {exporting === "csv" ? "Exporting..." : "CSV"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleDownload("json")}
                  disabled={exporting !== null}
                >
                  <ShieldAlert className="h-3.5 w-3.5" />
                  {exporting === "json" ? "Exporting..." : "JSON"}
                </Button>
              </div>
            </PanelHeader>
            <PanelBody className="space-y-4">
              {preview ? (
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3 text-xs">
                    <p className="mb-2 font-semibold text-zinc-200">
                      Preview Metrics ({preview.rows.length} rows)
                    </p>
                    <dl className="space-y-1">
                      {Object.entries(preview.summary_metrics).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2">
                          <dt className="text-zinc-400">{k.replaceAll("_", " ")}</dt>
                          <dd className="font-mono text-zinc-100">{String(v ?? "—")}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3 text-xs">
                    <p className="mb-2 font-semibold text-zinc-200">
                      Provenance & Methodological Limitations
                    </p>
                    <ul className="list-disc space-y-1 pl-4 text-[11px] text-zinc-400">
                      {preview.methodological_limitations.map((lim) => (
                        <li key={lim}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}
            </PanelBody>
          </Panel>
        </>
      ) : null}
    </div>
  );
}

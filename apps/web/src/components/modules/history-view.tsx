"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Download,
  FileJson,
  History,
  Plus,
  Search,
  Trash2,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FormError, Input, Select } from "@/components/ui/form-controls";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import {
  apiClient,
  ApiClientError,
  getDetectionAnnotatedUrl,
  getDetectionExportUrl,
} from "@/lib/api-client";
import type { DetectionJobRead, DetectionJobStatus, ModelRegistryItem } from "@/types/api";

const STATUS_TONE: Record<DetectionJobStatus, "emerald" | "amber" | "rose" | "neutral"> = {
  completed: "emerald",
  processing: "amber",
  queued: "neutral",
  failed: "rose",
  cancelled: "neutral",
};

export function HistoryView() {
  const { canOperate } = useAuth();
  const { refresh: refreshSystem } = useSystemState();
  const { notify } = useToast();

  const [jobs, setJobs] = React.useState<DetectionJobRead[]>([]);
  const [models, setModels] = React.useState<ModelRegistryItem[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Filters & Sorting
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const [modelFilter, setModelFilter] = React.useState("");
  const [reviewFilter, setReviewFilter] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [sortBy, setSortBy] = React.useState<"newest" | "oldest" | "duration_desc">("newest");

  React.useEffect(() => {
    apiClient
      .listModels()
      .then(setModels)
      .catch(() => {});
  }, []);

  const loadJobs = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.listDetectionJobs({
        q: search.trim() || undefined,
        status: statusFilter || undefined,
        model_id: modelFilter || undefined,
        review_status: reviewFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        sort_by: sortBy,
        limit: 100,
      });
      setJobs(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load detection history.");
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, modelFilter, reviewFilter, dateFrom, sortBy]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      void loadJobs();
    }, 150);
    return () => clearTimeout(timer);
  }, [loadJobs]);

  const handleDelete = async (job: DetectionJobRead) => {
    if (!window.confirm(`Delete detection job ${job.id.slice(0, 8)} and its annotated artifacts?`)) {
      return;
    }
    try {
      await apiClient.deleteDetectionJob(job.id);
      notify({ tone: "info", title: "Detection job deleted" });
      await Promise.all([loadJobs(), refreshSystem()]);
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: err instanceof ApiClientError ? err.message : "Unable to delete job.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Detection History"
        description="Auditable archive of AI detection runs, model provenance, human review status, JSON exports, and annotated downloads."
        phaseBadge="Phase 3 · Audit & Review Active"
        phaseTone="emerald"
        actions={
          canOperate && (
            <Button variant="primary" size="sm" asChild>
              <Link href="/detection">
                <Plus className="h-3.5 w-3.5" />
                <span>New Analysis</span>
              </Link>
            </Button>
          )
        }
      />

      {/* Search, Filter & Sort Toolbar */}
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-6">
        <div className="relative lg:col-span-2">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-zinc-500" />
          <Input
            type="search"
            placeholder="Search by filename, model, or scope..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            aria-label="Search detection jobs"
          />
        </div>
        <Select
          aria-label="Filter by job status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="completed">Completed</option>
          <option value="processing">Processing</option>
          <option value="queued">Queued</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </Select>
        <Select
          aria-label="Filter by model"
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
        >
          <option value="">All Models</option>
          {models.map((m) => (
            <option key={m.model_id} value={m.model_id}>
              {m.model_id}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filter by review status"
          value={reviewFilter}
          onChange={(e) => setReviewFilter(e.target.value)}
        >
          <option value="">Any Review State</option>
          <option value="unreviewed">Has Unreviewed</option>
          <option value="confirmed">Has Confirmed</option>
          <option value="rejected">Has Rejected</option>
          <option value="uncertain">Has Uncertain</option>
        </Select>
        <div className="flex gap-2">
          <Input
            type="date"
            aria-label="Filter from date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="flex-1"
          />
          <Select
            aria-label="Sort jobs"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "newest" | "oldest" | "duration_desc")}
            className="w-32"
          >
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="duration_desc">Slowest</option>
          </Select>
        </div>
      </div>

      {error && <FormError message={error} />}

      <Panel>
        <PanelHeader>
          <div>
            <PanelTitle>Executed Detection Jobs</PanelTitle>
            <PanelDescription>
              Real database records from <code className="font-mono text-zinc-300">GET /api/v1/detections/jobs</code>
            </PanelDescription>
          </div>
          <Badge tone="neutral" className="font-mono">
            {total} Total Jobs
          </Badge>
        </PanelHeader>
        <PanelBody className="p-0">
          {loading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : jobs.length === 0 ? (
            <div className="topo-grid flex min-h-[220px] flex-col items-center justify-center p-8 text-center">
              <History className="h-5 w-5 text-emerald-400" />
              <p className="mt-3 text-sm font-medium text-zinc-100">No detection jobs found</p>
              <p className="mt-1 max-w-md text-xs text-zinc-400">
                Run your first image or video analysis in AgroVision AI Detection to populate this history.
              </p>
              {canOperate && (
                <Button variant="primary" size="sm" asChild className="mt-4">
                  <Link href="/detection">Open AI Detection</Link>
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="px-5 py-3 font-semibold">Job & Model</th>
                    <th className="px-5 py-3 font-semibold">Media / Mode</th>
                    <th className="px-5 py-3 font-semibold">Status</th>
                    <th className="px-5 py-3 font-semibold">Detections & Review</th>
                    <th className="px-5 py-3 font-semibold">Duration</th>
                    <th className="px-5 py-3 font-semibold">Created</th>
                    <th className="px-5 py-3 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {jobs.map((job) => (
                    <tr key={job.id} className="transition-colors hover:bg-white/[0.025]">
                      <td className="px-5 py-3.5">
                        <Link
                          href={`/history/${job.id}`}
                          className="inline-flex items-center gap-1 font-medium text-zinc-100 hover:text-emerald-300"
                        >
                          <span className="font-mono">{job.id.slice(0, 8)}</span>
                          <ArrowUpRight className="h-3 w-3 text-zinc-500" />
                        </Link>
                        <div className="font-mono text-[10px] text-zinc-400">{job.model_id}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge tone="muted" className="font-mono uppercase">
                          {job.media_type} · {job.detection_mode}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge tone={STATUS_TONE[job.status]}>{job.status}</Badge>
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-zinc-300">
                        <div>{job.summary_json.total_detections ?? 0} objects</div>
                        {job.summary_json.review_counts && (
                          <div className="text-[10px] text-zinc-500">
                            {job.summary_json.review_counts.confirmed} ok ·{" "}
                            {job.summary_json.review_counts.rejected} rej ·{" "}
                            {job.summary_json.review_counts.unreviewed} unrev
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-emerald-300 tabular-nums">
                        {job.inference_ms !== null ? `${job.inference_ms} ms` : "—"}
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-zinc-400">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <div className="inline-flex items-center gap-1">
                          <Button variant="ghost" size="sm" asChild title="Inspect details">
                            <Link href={`/history/${job.id}`}>Inspect</Link>
                          </Button>
                          {job.annotated_storage_key && (
                            <Button variant="ghost" size="icon" asChild title="Download annotated JPG">
                              <a
                                href={getDetectionAnnotatedUrl(job.id, true)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Download className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                          )}
                          <Button variant="ghost" size="icon" asChild title="Export JSON">
                            <a href={getDetectionExportUrl(job.id)} target="_blank" rel="noreferrer">
                              <FileJson className="h-3.5 w-3.5" />
                            </a>
                          </Button>
                          {canOperate && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => void handleDelete(job)}
                              title="Delete job"
                            >
                              <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}

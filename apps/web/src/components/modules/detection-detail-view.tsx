"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, ShieldAlert } from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { DetectionInspector } from "@/components/modules/detection-inspector";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-controls";
import { Panel, PanelBody } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";
import type { DetectionJobDetailRead } from "@/types/api";

export function DetectionDetailView({ jobId }: { jobId: string }) {
  const { canOperate } = useAuth();
  const { notify } = useToast();
  const [job, setJob] = React.useState<DetectionJobDetailRead | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const loadJob = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getDetectionJob(jobId);
      setJob(data);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load detection job.");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  React.useEffect(() => {
    void loadJob();
  }, [loadJob]);

  const handleRetry = async () => {
    if (!job) return;
    try {
      const retried = await apiClient.retryDetectionJob(job.id);
      setJob(retried);
      notify({ tone: "info", title: "Job re-queued" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Retry failed",
        description: err instanceof ApiClientError ? err.message : "Unable to retry job.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={job ? `Detection Job · ${job.id.slice(0, 8)}` : "Detection Job Detail"}
        description={
          job
            ? `${job.model_name} (${job.model_version}) · ${job.media_asset?.original_filename ?? job.media_asset_id}`
            : "Inspect machine predictions, bounding boxes, and human verification records."
        }
        phaseBadge={job ? job.status.toUpperCase() : "Phase 3"}
        phaseTone={job?.status === "completed" ? "emerald" : "amber"}
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link href="/history">
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to History</span>
            </Link>
          </Button>
        }
      />

      {error && <FormError message={error} />}

      {loading ? (
        <Skeleton className="h-72 w-full rounded-xl" />
      ) : job && job.status === "completed" ? (
        <DetectionInspector job={job} onJobUpdated={setJob} />
      ) : job ? (
        <Panel>
          <PanelBody className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-400" />
              <div>
                <p className="text-sm font-semibold text-zinc-100">
                  Job Status: {job.status} ({job.progress_percent}%)
                </p>
                <p className="mt-1 text-xs text-zinc-400">
                  {job.error_message || "Analysis is not in completed state."}
                </p>
              </div>
            </div>
            {(job.status === "failed" || job.status === "cancelled") && canOperate && (
              <Button variant="primary" size="sm" onClick={() => void handleRetry()}>
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Retry Analysis</span>
              </Button>
            )}
          </PanelBody>
        </Panel>
      ) : null}
    </div>
  );
}

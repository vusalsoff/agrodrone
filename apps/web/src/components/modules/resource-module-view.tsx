"use client";

import * as React from "react";
import { CheckCircle2, Database, Layers } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api-client";

export type ResourceEndpointKey = "fields" | "missions" | "detections" | "alerts" | "none";

interface ResourceModuleViewProps {
  title: string;
  description: string;
  phaseBadge: string;
  endpointKey: ResourceEndpointKey;
  endpointPath: string;
  tableName: string;
  emptyHeadline: string;
  emptyDescription: string;
  plannedCapabilities: string[];
  schemaColumns: string[];
}

export function ResourceModuleView({
  title,
  description,
  phaseBadge,
  endpointKey,
  endpointPath,
  tableName,
  emptyHeadline,
  emptyDescription,
  plannedCapabilities,
  schemaColumns,
}: ResourceModuleViewProps) {
  const [total, setTotal] = React.useState<number | null>(endpointKey === "none" ? 0 : null);
  const [loading, setLoading] = React.useState<boolean>(endpointKey !== "none");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (endpointKey === "none") return;
    let active = true;

    const fetcher =
      endpointKey === "fields"
        ? apiClient.listFields
        : endpointKey === "missions"
          ? apiClient.listMissions
          : endpointKey === "detections"
            ? apiClient.listDetections
            : apiClient.listAlerts;

    fetcher()
      .then((res) => {
        if (active) setTotal(res.total);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : `Failed to reach ${endpointPath}`);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [endpointKey, endpointPath]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        description={description}
        phaseBadge={phaseBadge}
        phaseTone="neutral"
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Live Empty-State / Record Status Panel */}
        <Panel className="lg:col-span-8">
          <PanelHeader>
            <div>
              <PanelTitle>Live Data Store Status</PanelTitle>
              <PanelDescription>
                Connected endpoint:{" "}
                <code className="font-mono text-zinc-300">{endpointPath}</code>
              </PanelDescription>
            </div>
            <Badge tone={error ? "rose" : "emerald"} className="font-mono">
              {loading
                ? "Querying..."
                : error
                  ? "API Offline"
                  : `${total ?? 0} Persisted Records`}
            </Badge>
          </PanelHeader>
          <PanelBody>
            {loading ? (
              <Skeleton className="h-44 w-full rounded-xl" />
            ) : error ? (
              <div className="rounded-xl border border-rose-500/25 bg-rose-500/[0.06] p-6 text-xs text-rose-200">
                {error}
              </div>
            ) : (
              <div className="topo-grid flex min-h-[220px] flex-col items-center justify-center rounded-xl border border-dashed border-white/[0.10] bg-[#080B0A] p-8 text-center">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/[0.09] bg-white/[0.03]">
                  <Database className="h-5 w-5 text-emerald-400" />
                </div>
                <h3 className="mt-4 text-sm font-semibold text-zinc-100">{emptyHeadline}</h3>
                <p className="mt-1.5 max-w-lg text-xs leading-relaxed text-zinc-400">
                  {emptyDescription}
                </p>
              </div>
            )}
          </PanelBody>
        </Panel>

        {/* Architecture & Schema Blueprint */}
        <div className="space-y-4 lg:col-span-4">
          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Database Schema Readiness</PanelTitle>
                <PanelDescription className="font-mono text-[11px]">
                  table: {tableName}
                </PanelDescription>
              </div>
              <Layers className="h-4 w-4 text-zinc-400" />
            </PanelHeader>
            <PanelBody>
              <div className="flex flex-wrap gap-1.5">
                {schemaColumns.map((col) => (
                  <code
                    key={col}
                    className="rounded border border-white/[0.08] bg-white/[0.03] px-2 py-0.5 font-mono text-[11px] text-zinc-300"
                  >
                    {col}
                  </code>
                ))}
              </div>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Scheduled Deliverables</PanelTitle>
              </div>
            </PanelHeader>
            <PanelBody className="space-y-2 text-xs text-zinc-400">
              {plannedCapabilities.map((cap) => (
                <div key={cap} className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500/80" />
                  <span>{cap}</span>
                </div>
              ))}
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}

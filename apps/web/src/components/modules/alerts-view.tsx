"use client";

import * as React from "react";
import Link from "next/link";
import {
  Bell,
  CheckCircle2,
  MailWarning,
  Plus,
  RefreshCw,
  ShieldAlert,
  Sliders,
  Trash2,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { formatTimestamp } from "@/lib/utils";
import type {
  AlertPhase5Read,
  AlertRuleRead,
  AlertSeverity,
  AlertTriggerType,
  NotificationPreferenceRead,
  NotificationRead,
} from "@/types/api";

const SUPPORTED_YOLO_CLASSES = [
  "person",
  "bird",
  "cat",
  "dog",
  "horse",
  "sheep",
  "cow",
  "car",
  "truck",
  "bicycle",
  "motorcycle",
];

const TRIGGER_LABELS: Record<AlertTriggerType, string> = {
  yolo_class_detected: "YOLO Supported Class Detected",
  confidence_threshold_reached: "Confidence Threshold Reached",
  human_confirmed_detection: "Human-Confirmed Detection",
  ai_analysis_failed: "AI Analysis Failure",
  gateway_offline_ttl: "Gateway Offline Beyond Heartbeat TTL",
  mission_status_changed: "Mission Status Change",
};

function severityTone(sev: string): "rose" | "amber" | "neutral" {
  if (sev === "critical") return "rose";
  if (sev === "warning") return "amber";
  return "neutral";
}

function statusTone(st: string): "rose" | "amber" | "emerald" {
  if (st === "open") return "rose";
  if (st === "acknowledged") return "amber";
  return "emerald";
}

export function AlertsView() {
  const { canOperate } = useAuth();
  const { notify } = useToast();

  const [tab, setTab] = React.useState<"alerts" | "rules" | "notifications">("alerts");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [alerts, setAlerts] = React.useState<AlertPhase5Read[]>([]);
  const [rules, setRules] = React.useState<AlertRuleRead[]>([]);
  const [notifications, setNotifications] = React.useState<NotificationRead[]>([]);
  const [prefs, setPrefs] = React.useState<NotificationPreferenceRead | null>(null);

  const [statusFilter, setStatusFilter] = React.useState<string>("");
  const [severityFilter, setSeverityFilter] = React.useState<string>("");

  // Rule creation form
  const [ruleName, setRuleName] = React.useState("");
  const [triggerType, setTriggerType] = React.useState<AlertTriggerType>("yolo_class_detected");
  const [ruleSeverity, setRuleSeverity] = React.useState<AlertSeverity>("warning");
  const [selectedClasses, setSelectedClasses] = React.useState<string[]>(["bird"]);
  const [minConfidence, setMinConfidence] = React.useState<string>("0.65");
  const [cooldownMinutes, setCooldownMinutes] = React.useState<string>("15");
  const [creatingRule, setCreatingRule] = React.useState(false);

  const loadAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [aRes, rRes, nRes, pRes] = await Promise.all([
        apiClient.listAlertsPhase5({
          status: statusFilter || undefined,
          severity: severityFilter || undefined,
          limit: 50,
        }),
        apiClient.listAlertRules(50, 0),
        apiClient.listNotifications({ limit: 50 }),
        apiClient.getNotificationPreferences(),
      ]);
      setAlerts(aRes.items);
      setRules(rRes.items);
      setNotifications(nRes.items);
      setPrefs(pRes);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load alerts & rules.");
    } finally {
      setLoading(false);
    }
  }, [severityFilter, statusFilter]);

  React.useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleEvaluateGateways = async () => {
    try {
      const res = await apiClient.evaluateGatewayAlerts();
      notify({
        tone: "info",
        title: "Gateway TTL evaluation complete",
        description: `Checked ${res.checked_gateways} active gateway(s); ${res.offline_detected} offline, ${res.alerts_created} alert(s) created.`,
      });
      await loadAll();
    } catch (err) {
      notify({
        tone: "error",
        title: "Evaluation failed",
        description: err instanceof ApiClientError ? err.message : "Could not evaluate gateways.",
      });
    }
  };

  const handleAcknowledge = async (alertId: string) => {
    try {
      const updated = await apiClient.acknowledgeAlert(alertId);
      setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      notify({ tone: "success", title: "Alert acknowledged" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Action failed",
        description: err instanceof ApiClientError ? err.message : "Could not acknowledge alert.",
      });
    }
  };

  const handleResolve = async (alertId: string) => {
    try {
      const updated = await apiClient.resolveAlert(alertId, "Resolved via Alerts Console.");
      setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      notify({ tone: "success", title: "Alert resolved" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Action failed",
        description: err instanceof ApiClientError ? err.message : "Could not resolve alert.",
      });
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleName.trim()) return;
    setCreatingRule(true);
    try {
      const created = await apiClient.createAlertRule({
        name: ruleName.trim(),
        severity: ruleSeverity,
        trigger_type: triggerType,
        target_classes: triggerType === "yolo_class_detected" ? selectedClasses : [],
        min_confidence:
          triggerType === "yolo_class_detected" || triggerType === "confidence_threshold_reached"
            ? Number(minConfidence)
            : null,
        cooldown_minutes: Number(cooldownMinutes) || 15,
      });
      setRules((prev) => [created, ...prev]);
      setRuleName("");
      notify({ tone: "success", title: "Alert rule created", description: created.name });
    } catch (err) {
      notify({
        tone: "error",
        title: "Rule rejected",
        description: err instanceof ApiClientError ? err.message : "Invalid rule configuration.",
      });
    } finally {
      setCreatingRule(false);
    }
  };

  const handleToggleRule = async (rule: AlertRuleRead) => {
    try {
      const updated = await apiClient.updateAlertRule(rule.id, { enabled: !rule.enabled });
      setRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (err) {
      notify({
        tone: "error",
        title: "Failed to toggle rule",
        description: err instanceof ApiClientError ? err.message : "Update failed.",
      });
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await apiClient.deleteAlertRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      notify({ tone: "info", title: "Alert rule deleted" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Failed to delete rule",
        description: err instanceof ApiClientError ? err.message : "Delete failed.",
      });
    }
  };

  const handleMarkNotifRead = async (notifId: string) => {
    try {
      const updated = await apiClient.markNotificationRead(notifId);
      setNotifications((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
    } catch {
      // ignore
    }
  };

  const handleToggleInAppPrefs = async () => {
    if (!prefs) return;
    try {
      const updated = await apiClient.updateNotificationPreferences({
        in_app_enabled: !prefs.in_app_enabled,
      });
      setPrefs(updated);
    } catch (err) {
      notify({
        tone: "error",
        title: "Failed to update preferences",
        description: err instanceof ApiClientError ? err.message : "Update failed.",
      });
    }
  };

  const openCount = alerts.filter((a) => a.status === "open").length;
  const unreadNotifs = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="space-y-6">
      <PageHeader
        phaseBadge="Phase 5 · Alerting & Notification Center"
        phaseTone="emerald"
        title="Alerts & Notifications"
        description="Event-driven alert rules, deduplication/cooldowns, ESP32-CAM gateway TTL checks, and persistent in-app notifications."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void handleEvaluateGateways()}>
              <ShieldAlert className="h-3.5 w-3.5" />
              Evaluate Gateway TTLs
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2">
        <Button
          variant={tab === "alerts" ? "primary" : "outline"}
          size="sm"
          onClick={() => setTab("alerts")}
        >
          <ShieldAlert className="h-3.5 w-3.5" />
          Alert Queue ({openCount} open)
        </Button>
        <Button
          variant={tab === "rules" ? "primary" : "outline"}
          size="sm"
          onClick={() => setTab("rules")}
        >
          <Sliders className="h-3.5 w-3.5" />
          Alert Rules ({rules.length})
        </Button>
        <Button
          variant={tab === "notifications" ? "primary" : "outline"}
          size="sm"
          onClick={() => setTab("notifications")}
        >
          <Bell className="h-3.5 w-3.5" />
          Notification Center ({unreadNotifs} unread)
        </Button>
      </div>

      {error ? (
        <Panel className="border-rose-500/30">
          <PanelBody className="text-sm text-rose-300">{error}</PanelBody>
        </Panel>
      ) : null}

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : null}

      {!loading && tab === "alerts" ? (
        <Panel>
          <PanelHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <PanelTitle>Operational Alert History</PanelTitle>
              <PanelDescription>
                Every alert is created from a real detection, mission transition, or gateway heartbeat TTL check.
              </PanelDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter alert status"
                className="rounded-lg border border-white/[0.1] bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-200"
              >
                <option value="">All Statuses</option>
                <option value="open">Open</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="resolved">Resolved</option>
              </select>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                aria-label="Filter alert severity"
                className="rounded-lg border border-white/[0.1] bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-200"
              >
                <option value="">All Severities</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
            </div>
          </PanelHeader>
          <PanelBody>
            {alerts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/[0.1] p-8 text-center">
                <p className="text-sm font-medium text-zinc-200">No operational alerts</p>
                <p className="mt-1 text-xs text-zinc-400">
                  Create an alert rule under Alert Rules to trigger alerts on real detections, mission updates, or gateway TTL expiry.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="flex flex-col justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 sm:flex-row sm:items-center"
                  >
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge>
                        <Badge tone={statusTone(alert.status)}>{alert.status}</Badge>
                        <span className="font-mono text-[11px] text-zinc-400">{alert.category}</span>
                      </div>
                      <p className="text-sm font-medium text-zinc-100">{alert.title}</p>
                      <p className="text-xs text-zinc-400">{alert.message}</p>
                      <p className="text-[11px] text-zinc-500">
                        Triggered {formatTimestamp(alert.created_at)}
                        {alert.acknowledged_at ? ` · Ack ${formatTimestamp(alert.acknowledged_at)}` : ""}
                        {alert.resolved_at ? ` · Resolved ${formatTimestamp(alert.resolved_at)}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      {alert.detection_job_id ? (
                        <Button variant="ghost" size="sm" asChild>
                          <Link href={`/history/${alert.detection_job_id}`}>View Job</Link>
                        </Button>
                      ) : null}
                      {canOperate && alert.status === "open" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleAcknowledge(alert.id)}
                        >
                          Acknowledge
                        </Button>
                      ) : null}
                      {canOperate && alert.status !== "resolved" ? (
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => void handleResolve(alert.id)}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Resolve
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </PanelBody>
        </Panel>
      ) : null}

      {!loading && tab === "rules" ? (
        <div className="grid gap-6 lg:grid-cols-12">
          {canOperate ? (
            <Panel className="lg:col-span-5">
              <PanelHeader>
                <PanelTitle>Create Alert Rule</PanelTitle>
                <PanelDescription>
                  YOLO class triggers are strictly limited to supported baseline COCO classes.
                </PanelDescription>
              </PanelHeader>
              <PanelBody>
                <form onSubmit={(e) => void handleCreateRule(e)} className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs text-zinc-400">Rule Name</label>
                    <input
                      type="text"
                      required
                      value={ruleName}
                      onChange={(e) => setRuleName(e.target.value)}
                      placeholder="e.g. Field Bird Activity"
                      className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-3 py-2 text-xs text-zinc-100"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs text-zinc-400">Trigger Event</label>
                      <select
                        value={triggerType}
                        onChange={(e) => setTriggerType(e.target.value as AlertTriggerType)}
                        className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-2.5 py-2 text-xs text-zinc-100"
                      >
                        {Object.entries(TRIGGER_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-zinc-400">Severity</label>
                      <select
                        value={ruleSeverity}
                        onChange={(e) => setRuleSeverity(e.target.value as AlertSeverity)}
                        className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-2.5 py-2 text-xs text-zinc-100"
                      >
                        <option value="info">Info</option>
                        <option value="warning">Warning</option>
                        <option value="critical">Critical</option>
                      </select>
                    </div>
                  </div>
                  {triggerType === "yolo_class_detected" ? (
                    <div>
                      <label className="mb-1 block text-xs text-zinc-400">
                        Supported YOLOv8n Classes
                      </label>
                      <div className="flex flex-wrap gap-1.5">
                        {SUPPORTED_YOLO_CLASSES.map((cls) => {
                          const active = selectedClasses.includes(cls);
                          return (
                            <button
                              key={cls}
                              type="button"
                              onClick={() =>
                                setSelectedClasses((prev) =>
                                  prev.includes(cls) ? prev.filter((c) => c !== cls) : [...prev, cls],
                                )
                              }
                              className={`rounded-md border px-2 py-1 text-[11px] transition-colors ${
                                active
                                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
                                  : "border-white/[0.08] bg-white/[0.02] text-zinc-400"
                              }`}
                            >
                              {cls}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs text-zinc-400">Min Confidence</label>
                      <input
                        type="number"
                        step="0.05"
                        min="0.05"
                        max="0.99"
                        value={minConfidence}
                        onChange={(e) => setMinConfidence(e.target.value)}
                        className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-3 py-2 text-xs text-zinc-100"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-zinc-400">Cooldown (min)</label>
                      <input
                        type="number"
                        min="0"
                        max="10080"
                        value={cooldownMinutes}
                        onChange={(e) => setCooldownMinutes(e.target.value)}
                        className="w-full rounded-lg border border-white/[0.1] bg-zinc-950 px-3 py-2 text-xs text-zinc-100"
                      />
                    </div>
                  </div>
                  <Button type="submit" variant="primary" size="sm" disabled={creatingRule}>
                    <Plus className="h-3.5 w-3.5" />
                    {creatingRule ? "Saving..." : "Create Rule"}
                  </Button>
                </form>
              </PanelBody>
            </Panel>
          ) : null}

          <Panel className={canOperate ? "lg:col-span-7" : "lg:col-span-12"}>
            <PanelHeader>
              <PanelTitle>Configured Rules</PanelTitle>
              <PanelDescription>Deduplicated per event with configurable cooldown windows.</PanelDescription>
            </PanelHeader>
            <PanelBody>
              {rules.length === 0 ? (
                <p className="py-6 text-center text-xs text-zinc-400">No alert rules configured yet.</p>
              ) : (
                <div className="space-y-3">
                  {rules.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3.5"
                    >
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-zinc-100">{rule.name}</span>
                          <Badge tone={severityTone(rule.severity)}>{rule.severity}</Badge>
                          <Badge tone={rule.enabled ? "emerald" : "neutral"}>
                            {rule.enabled ? "Enabled" : "Disabled"}
                          </Badge>
                        </div>
                        <p className="text-xs text-zinc-400">
                          {TRIGGER_LABELS[rule.trigger_type] ?? rule.trigger_type} · Cooldown {rule.cooldown_minutes}m
                          {rule.target_classes.length > 0 ? ` · Classes: ${rule.target_classes.join(", ")}` : ""}
                        </p>
                      </div>
                      {canOperate ? (
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleToggleRule(rule)}
                          >
                            {rule.enabled ? "Disable" : "Enable"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => void handleDeleteRule(rule.id)}
                            aria-label="Delete alert rule"
                          >
                            <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </PanelBody>
          </Panel>
        </div>
      ) : null}

      {!loading && tab === "notifications" ? (
        <div className="grid gap-6 lg:grid-cols-12">
          <Panel className="lg:col-span-8">
            <PanelHeader>
              <PanelTitle>In-App Notification Feed</PanelTitle>
              <PanelDescription>Persistent notifications linked to real alert records.</PanelDescription>
            </PanelHeader>
            <PanelBody>
              {notifications.length === 0 ? (
                <p className="py-6 text-center text-xs text-zinc-400">No notifications yet.</p>
              ) : (
                <div className="space-y-2.5">
                  {notifications.map((n) => (
                    <div
                      key={n.id}
                      className="flex items-start justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3.5"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Badge tone={severityTone(n.severity)}>{n.severity}</Badge>
                          <span className="text-sm font-medium text-zinc-100">{n.title}</span>
                          {!n.is_read ? <Badge tone="emerald">Unread</Badge> : null}
                        </div>
                        <p className="text-xs text-zinc-400">{n.message}</p>
                        <p className="text-[11px] text-zinc-500">{formatTimestamp(n.created_at)}</p>
                      </div>
                      {!n.is_read ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleMarkNotifRead(n.id)}
                        >
                          Mark Read
                        </Button>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </PanelBody>
          </Panel>

          <Panel className="lg:col-span-4">
            <PanelHeader>
              <PanelTitle>Notification Preferences</PanelTitle>
              <PanelDescription>Per-user channel configuration.</PanelDescription>
            </PanelHeader>
            <PanelBody className="space-y-4">
              {prefs ? (
                <>
                  <div className="flex items-center justify-between rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
                    <div>
                      <p className="text-xs font-medium text-zinc-100">In-App Notifications</p>
                      <p className="text-[11px] text-zinc-400">
                        Minimum severity: {prefs.min_severity}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleToggleInAppPrefs()}
                    >
                      {prefs.in_app_enabled ? "Enabled" : "Disabled"}
                    </Button>
                  </div>

                  <div className="rounded-lg border border-amber-500/25 bg-amber-500/[0.05] p-3">
                    <div className="flex items-center gap-2 text-xs font-medium text-amber-200">
                      <MailWarning className="h-4 w-4 shrink-0" />
                      <span>
                        Email Delivery: {prefs.email_available ? "Configured" : "Unavailable"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-zinc-400">{prefs.email_status_reason}</p>
                  </div>
                </>
              ) : null}
            </PanelBody>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

"use client";

import * as React from "react";
import {
  CheckCircle2,
  ClipboardList,
  Compass,
  Image as ImageIcon,
  MessageSquarePlus,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FieldLabel,
  FormError,
  Input,
  Select,
  Textarea,
} from "@/components/ui/form-controls";
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
import type {
  DeviceRead,
  FieldRead,
  MediaAssetRead,
  MissionRead,
  MissionStatus,
} from "@/types/api";

const STATUS_BADGE: Record<
  MissionStatus,
  { tone: "emerald" | "amber" | "rose" | "neutral"; label: string }
> = {
  draft: { tone: "neutral", label: "Draft" },
  planned: { tone: "amber", label: "Planned" },
  in_progress: { tone: "emerald", label: "In Progress" },
  completed: { tone: "emerald", label: "Completed" },
  cancelled: { tone: "rose", label: "Cancelled" },
};

const NEXT_TRANSITIONS: Record<MissionStatus, Array<{ target: MissionStatus; label: string }>> = {
  draft: [
    { target: "planned", label: "Mark Planned" },
    { target: "in_progress", label: "Start Mission" },
    { target: "cancelled", label: "Cancel" },
  ],
  planned: [
    { target: "in_progress", label: "Start Mission" },
    { target: "draft", label: "Return to Draft" },
    { target: "cancelled", label: "Cancel" },
  ],
  in_progress: [
    { target: "completed", label: "Complete Mission" },
    { target: "cancelled", label: "Cancel" },
  ],
  completed: [],
  cancelled: [{ target: "draft", label: "Reopen as Draft" }],
};

export function MissionsView() {
  const { canOperate } = useAuth();
  const { refresh: refreshSystem } = useSystemState();
  const { notify } = useToast();

  const [missions, setMissions] = React.useState<MissionRead[]>([]);
  const [fields, setFields] = React.useState<FieldRead[]>([]);
  const [devices, setDevices] = React.useState<DeviceRead[]>([]);
  const [missionMedia, setMissionMedia] = React.useState<MediaAssetRead[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  // Observation & inline upload state
  const [obsText, setObsText] = React.useState("");
  const [obsSubmitting, setObsSubmitting] = React.useState(false);
  const [transitioning, setTransitioning] = React.useState(false);
  const [uploadPercent, setUploadPercent] = React.useState<number | null>(null);

  // Create / Edit modal state
  const [modalOpen, setModalOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<MissionRead | null>(null);
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [fieldId, setFieldId] = React.useState("");
  const [deviceId, setDeviceId] = React.useState("");
  const [initialStatus, setInitialStatus] = React.useState<"draft" | "planned">("draft");
  const [operatorNotes, setOperatorNotes] = React.useState("");
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const loadMissions = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mRes, fRes, dRes] = await Promise.all([
        apiClient.listMissions({
          q: search.trim() || undefined,
          status: statusFilter || undefined,
          limit: 100,
        }),
        apiClient.listFields({ limit: 200 }),
        apiClient.listDevices({ limit: 200 }),
      ]);
      setMissions(mRes.items);
      setTotal(mRes.total);
      setFields(fRes.items);
      setDevices(dRes.items);
      if (mRes.items.length > 0 && !selectedId) {
        setSelectedId(mRes.items[0].id);
      }
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load missions.");
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, selectedId]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      void loadMissions();
    }, 150);
    return () => clearTimeout(timer);
  }, [loadMissions]);

  const selectedMission = React.useMemo(
    () => missions.find((m) => m.id === selectedId) ?? null,
    [missions, selectedId],
  );

  const loadMissionMedia = React.useCallback(async (missionId: string) => {
    try {
      const res = await apiClient.listMedia({ mission_id: missionId, limit: 50 });
      setMissionMedia(res.items);
    } catch {
      setMissionMedia([]);
    }
  }, []);

  React.useEffect(() => {
    if (selectedMission) {
      void loadMissionMedia(selectedMission.id);
    } else {
      setMissionMedia([]);
    }
  }, [selectedMission, loadMissionMedia]);

  const fieldLabel = React.useCallback(
    (id: string | null) => {
      if (!id) return "Unassigned";
      const found = fields.find((f) => f.id === id);
      return found ? `${found.name} (${found.code})` : "Assigned Field";
    },
    [fields],
  );

  const deviceLabel = React.useCallback(
    (id: string | null) => {
      if (!id) return "Unassigned";
      const found = devices.find((d) => d.id === id);
      return found ? found.name : "Assigned Device";
    },
    [devices],
  );

  const openCreateModal = () => {
    setEditing(null);
    setTitle("");
    setDescription("");
    setFieldId(fields[0]?.id ?? "");
    setDeviceId(devices[0]?.id ?? "");
    setInitialStatus("draft");
    setOperatorNotes("");
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (mission: MissionRead) => {
    setEditing(mission);
    setTitle(mission.title);
    setDescription(mission.description ?? "");
    setFieldId(mission.field_id ?? "");
    setDeviceId(mission.device_id ?? "");
    setOperatorNotes(mission.operator_notes ?? "");
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (title.trim().length < 2) {
      setFormError("Mission title must be at least 2 characters.");
      return;
    }

    setSubmitting(true);
    try {
      if (editing) {
        const updated = await apiClient.updateMission(editing.id, {
          title: title.trim(),
          description: description.trim() || null,
          field_id: fieldId || undefined,
          unassign_field: !fieldId,
          device_id: deviceId || undefined,
          unassign_device: !deviceId,
          operator_notes: operatorNotes.trim() || null,
        });
        setMissions((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
        notify({ tone: "success", title: "Mission updated", description: updated.title });
      } else {
        const created = await apiClient.createMission({
          title: title.trim(),
          description: description.trim() || null,
          field_id: fieldId || null,
          device_id: deviceId || null,
          status: initialStatus,
          operator_notes: operatorNotes.trim() || null,
        });
        setSelectedId(created.id);
        notify({ tone: "success", title: "Mission created", description: created.title });
      }
      setModalOpen(false);
      await Promise.all([loadMissions(), refreshSystem()]);
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Failed to save mission.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTransition = async (target: MissionStatus) => {
    if (!selectedMission) return;
    setTransitioning(true);
    try {
      const updated = await apiClient.transitionMission(selectedMission.id, target);
      setMissions((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      notify({
        tone: "success",
        title: `Mission → ${STATUS_BADGE[target].label}`,
        description: updated.title,
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Transition blocked",
        description: err instanceof ApiClientError ? err.message : "Invalid transition.",
      });
    } finally {
      setTransitioning(false);
    }
  };

  const handleAddObservation = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedMission || obsText.trim().length < 2) return;
    setObsSubmitting(true);
    try {
      const updated = await apiClient.addMissionObservation(selectedMission.id, obsText.trim());
      setMissions((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setObsText("");
      notify({ tone: "success", title: "Observation logged" });
    } catch (err) {
      notify({
        tone: "error",
        title: "Failed to log observation",
        description: err instanceof ApiClientError ? err.message : "Error saving note.",
      });
    } finally {
      setObsSubmitting(false);
    }
  };

  const handleMissionImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedMission) return;
    setUploadPercent(0);
    try {
      await uploadMediaWithProgress(
        {
          file,
          missionId: selectedMission.id,
          fieldId: selectedMission.field_id,
        },
        (pct) => setUploadPercent(pct),
      );
      notify({ tone: "success", title: "Media attached", description: file.name });
      await Promise.all([loadMissionMedia(selectedMission.id), refreshSystem()]);
    } catch (err) {
      notify({
        tone: "error",
        title: "Upload failed",
        description: err instanceof ApiClientError ? err.message : "Rejected by security validation.",
      });
    } finally {
      setUploadPercent(null);
    }
  };

  const handleDelete = async (mission: MissionRead) => {
    if (!window.confirm(`Delete mission "${mission.title}"?`)) return;
    try {
      await apiClient.deleteMission(mission.id);
      if (selectedId === mission.id) setSelectedId(null);
      notify({ tone: "info", title: "Mission deleted", description: mission.title });
      await Promise.all([loadMissions(), refreshSystem()]);
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: err instanceof ApiClientError ? err.message : "Unable to delete mission.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Mission Management"
        description="Plan and log manual E88 + ESP32-CAM field surveys, lifecycle transitions, manual observations, and captured imagery."
        phaseBadge="Phase 2 · Mission Lifecycle Active"
        phaseTone="emerald"
        actions={
          canOperate && (
            <Button variant="primary" size="sm" onClick={openCreateModal}>
              <Plus className="h-3.5 w-3.5" />
              <span>New Mission</span>
            </Button>
          )
        }
      />

      {/* Search & Status Filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-zinc-500" />
          <Input
            type="search"
            placeholder="Search missions by title or notes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            aria-label="Search missions"
          />
        </div>
        <div className="flex items-center gap-2">
          <Select
            aria-label="Filter missions by status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-44"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="planned">Planned</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </Select>
          <Badge tone="neutral" className="font-mono">
            {total} Missions
          </Badge>
        </div>
      </div>

      {error && <FormError message={error} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Missions List */}
        <Panel className="lg:col-span-5">
          <PanelHeader>
            <div>
              <PanelTitle>Survey Missions</PanelTitle>
              <PanelDescription>Manual capture logs (no simulated autopilot).</PanelDescription>
            </div>
          </PanelHeader>
          <PanelBody className="space-y-2">
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : missions.length === 0 ? (
              <div className="topo-grid flex min-h-[220px] flex-col items-center justify-center rounded-lg border border-dashed border-white/[0.09] p-6 text-center">
                <Compass className="h-5 w-5 text-emerald-400" />
                <p className="mt-3 text-sm font-medium text-zinc-100">No missions recorded yet</p>
                <p className="mt-1 text-xs text-zinc-400">
                  Create a draft or planned survey mission and attach field imagery after flight.
                </p>
                {canOperate && (
                  <Button variant="primary" size="sm" onClick={openCreateModal} className="mt-4">
                    <Plus className="h-3.5 w-3.5" />
                    <span>Create First Mission</span>
                  </Button>
                )}
              </div>
            ) : (
              missions.map((mission) => {
                const badge = STATUS_BADGE[mission.status];
                const active = mission.id === selectedId;
                return (
                  <button
                    key={mission.id}
                    type="button"
                    onClick={() => setSelectedId(mission.id)}
                    className={`w-full rounded-xl border p-3.5 text-left transition-colors ${
                      active
                        ? "border-emerald-500/35 bg-emerald-500/[0.09]"
                        : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium text-zinc-100">{mission.title}</span>
                      <Badge tone={badge.tone}>{badge.label}</Badge>
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-zinc-400">
                      <span>Field: {fieldLabel(mission.field_id)}</span>
                      <span>Device: {deviceLabel(mission.device_id)}</span>
                    </div>
                  </button>
                );
              })
            )}
          </PanelBody>
        </Panel>

        {/* Right: Mission Detail, Lifecycle Transitions, Observations & Attached Media */}
        <div className="space-y-6 lg:col-span-7">
          {!selectedMission ? (
            <Panel>
              <PanelBody className="flex min-h-[280px] flex-col items-center justify-center text-center">
                <ClipboardList className="h-5 w-5 text-zinc-500" />
                <p className="mt-2.5 text-xs text-zinc-400">
                  Select a mission from the list to manage its lifecycle, observations, and media.
                </p>
              </PanelBody>
            </Panel>
          ) : (
            <>
              <Panel>
                <PanelHeader>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <PanelTitle className="text-base">{selectedMission.title}</PanelTitle>
                      <Badge tone={STATUS_BADGE[selectedMission.status].tone}>
                        {STATUS_BADGE[selectedMission.status].label}
                      </Badge>
                    </div>
                    <PanelDescription>
                      Manual Flight Log · E88 does not expose an autonomous flight-control API.
                    </PanelDescription>
                  </div>
                  {canOperate && (
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEditModal(selectedMission)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => void handleDelete(selectedMission)}>
                        <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                      </Button>
                    </div>
                  )}
                </PanelHeader>
                <PanelBody className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                    <div className="rounded-lg bg-white/[0.025] p-2.5">
                      <span className="text-[10px] uppercase text-zinc-500">Assigned Field</span>
                      <p className="mt-0.5 truncate font-medium text-zinc-200">
                        {fieldLabel(selectedMission.field_id)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white/[0.025] p-2.5">
                      <span className="text-[10px] uppercase text-zinc-500">Assigned Device</span>
                      <p className="mt-0.5 truncate font-medium text-zinc-200">
                        {deviceLabel(selectedMission.device_id)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white/[0.025] p-2.5">
                      <span className="text-[10px] uppercase text-zinc-500">Started</span>
                      <p className="mt-0.5 font-mono text-[11px] text-zinc-300">
                        {selectedMission.started_at
                          ? new Date(selectedMission.started_at).toLocaleString()
                          : "—"}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white/[0.025] p-2.5">
                      <span className="text-[10px] uppercase text-zinc-500">Completed</span>
                      <p className="mt-0.5 font-mono text-[11px] text-zinc-300">
                        {selectedMission.completed_at
                          ? new Date(selectedMission.completed_at).toLocaleString()
                          : "—"}
                      </p>
                    </div>
                  </div>

                  {selectedMission.description && (
                    <p className="text-xs leading-relaxed text-zinc-300">
                      {selectedMission.description}
                    </p>
                  )}

                  {selectedMission.operator_notes && (
                    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-zinc-400">
                      <span className="font-semibold text-zinc-200">Preflight / Operator Notes: </span>
                      {selectedMission.operator_notes}
                    </div>
                  )}

                  {/* Validated State Transition Buttons */}
                  {canOperate && NEXT_TRANSITIONS[selectedMission.status].length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
                      <span className="text-[11px] font-medium text-zinc-500">Lifecycle:</span>
                      {NEXT_TRANSITIONS[selectedMission.status].map((t) => (
                        <Button
                          key={t.target}
                          variant={
                            t.target === "in_progress" || t.target === "completed"
                              ? "primary"
                              : t.target === "cancelled"
                                ? "outline"
                                : "secondary"
                          }
                          size="sm"
                          disabled={transitioning}
                          onClick={() => void handleTransition(t.target)}
                        >
                          {t.target === "in_progress" && <Play className="h-3.5 w-3.5" />}
                          {t.target === "completed" && <CheckCircle2 className="h-3.5 w-3.5" />}
                          {t.target === "cancelled" && <XCircle className="h-3.5 w-3.5 text-rose-400" />}
                          {t.target === "draft" && <RotateCcw className="h-3.5 w-3.5" />}
                          <span>{t.label}</span>
                        </Button>
                      ))}
                    </div>
                  )}
                </PanelBody>
              </Panel>

              {/* Manual Observations Timeline */}
              <Panel>
                <PanelHeader>
                  <div>
                    <PanelTitle>Manual Field Observations</PanelTitle>
                    <PanelDescription>Timestamped operator notes recorded before, during, or after capture.</PanelDescription>
                  </div>
                  <Badge tone="neutral" className="font-mono">
                    {selectedMission.observations.length} Logged
                  </Badge>
                </PanelHeader>
                <PanelBody className="space-y-3">
                  {canOperate && (
                    <form onSubmit={(e) => void handleAddObservation(e)} className="flex gap-2">
                      <Input
                        placeholder="Record manual observation (e.g., wind gusts, dry patch in row 4)..."
                        value={obsText}
                        onChange={(e) => setObsText(e.target.value)}
                      />
                      <Button
                        type="submit"
                        variant="subtle"
                        size="md"
                        disabled={obsSubmitting || obsText.trim().length < 2}
                      >
                        <MessageSquarePlus className="h-4 w-4" />
                        <span>Add</span>
                      </Button>
                    </form>
                  )}

                  {selectedMission.observations.length === 0 ? (
                    <p className="text-xs text-zinc-500">No observations recorded for this mission yet.</p>
                  ) : (
                    <ul className="space-y-2">
                      {[...selectedMission.observations].reverse().map((obs) => (
                        <li
                          key={obs.id}
                          className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5 text-xs"
                        >
                          <div className="flex items-center justify-between text-[10px] text-zinc-500">
                            <span className="font-medium text-zinc-300">{obs.author_name}</span>
                            <span className="font-mono">
                              {new Date(obs.recorded_at).toLocaleString()}
                            </span>
                          </div>
                          <p className="mt-1 text-zinc-200">{obs.note}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </PanelBody>
              </Panel>

              {/* Associated Mission Media */}
              <Panel>
                <PanelHeader>
                  <div>
                    <PanelTitle>Associated Mission Media</PanelTitle>
                    <PanelDescription>Upload verified ESP32-CAM or field imagery directly to this mission.</PanelDescription>
                  </div>
                  {canOperate && (
                    <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20">
                      <Upload className="h-3.5 w-3.5" />
                      <span>{uploadPercent !== null ? `Uploading ${uploadPercent}%` : "Attach Media"}</span>
                      <input
                        type="file"
                        accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime"
                        className="sr-only"
                        onChange={(e) => void handleMissionImageUpload(e)}
                        disabled={uploadPercent !== null}
                      />
                    </label>
                  )}
                </PanelHeader>
                <PanelBody>
                  {missionMedia.length === 0 ? (
                    <div className="flex items-center gap-2 text-xs text-zinc-500">
                      <ImageIcon className="h-4 w-4" />
                      <span>No images or videos attached to this mission yet.</span>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {missionMedia.map((item) => (
                        <div
                          key={item.id}
                          className="overflow-hidden rounded-lg border border-white/[0.08] bg-[#090D0B]"
                        >
                          {item.media_type === "image" ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={getMediaContentUrl(item.id)}
                              alt={item.original_filename}
                              className="h-24 w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-24 items-center justify-center font-mono text-[11px] text-zinc-400">
                              VIDEO · {item.mime_type}
                            </div>
                          )}
                          <div className="truncate px-2.5 py-1.5 font-mono text-[10px] text-zinc-300">
                            {item.original_filename}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </PanelBody>
              </Panel>
            </>
          )}
        </div>
      </div>

      {/* Create / Edit Mission Modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Edit Mission" : "Create Field Survey Mission"}
        description="Log a manual flight or ground capture session assigned to a field and registered hardware."
      >
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <FormError message={formError} />

          <div>
            <FieldLabel htmlFor="mission-title" required>
              Mission Title
            </FieldLabel>
            <Input
              id="mission-title"
              placeholder="e.g., Block A Morning Canopy Sweep"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="mission-field">Assigned Field</FieldLabel>
              <Select
                id="mission-field"
                value={fieldId}
                onChange={(e) => setFieldId(e.target.value)}
              >
                <option value="">Unassigned</option>
                {fields.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name} ({f.code})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <FieldLabel htmlFor="mission-device">Assigned Device</FieldLabel>
              <Select
                id="mission-device"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
              >
                <option value="">Unassigned</option>
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.device_identifier || d.hardware_model})
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {!editing && (
            <div>
              <FieldLabel htmlFor="mission-status">Initial Status</FieldLabel>
              <Select
                id="mission-status"
                value={initialStatus}
                onChange={(e) => setInitialStatus(e.target.value as "draft" | "planned")}
              >
                <option value="draft">Draft</option>
                <option value="planned">Planned</option>
              </Select>
            </div>
          )}

          <div>
            <FieldLabel htmlFor="mission-desc">Mission Objective / Description</FieldLabel>
            <Textarea
              id="mission-desc"
              placeholder="Target crop rows, inspection goal, capture height estimate..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div>
            <FieldLabel htmlFor="mission-notes">Manual Preflight & Weather Notes</FieldLabel>
            <Textarea
              id="mission-notes"
              placeholder="e.g., Clear morning sun, light breeze, OV2640 set to SVGA..."
              value={operatorNotes}
              onChange={(e) => setOperatorNotes(e.target.value)}
            />
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-white/[0.07] pt-4">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Saving..." : editing ? "Save Mission" : "Create Mission"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

"use client";

import * as React from "react";
import { Check, Cpu, MinusCircle, Pencil, Plus, Search, Trash2, WifiOff } from "lucide-react";

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
import { apiClient, ApiClientError } from "@/lib/api-client";
import type {
  ConnectivityMode,
  DeviceRead,
  DeviceStatus,
  DeviceType,
  FieldRead,
} from "@/types/api";

function deviceStatusBadge(status: string): { tone: "amber" | "neutral" | "rose"; label: string } {
  switch (status) {
    case "offline_isolated_ap":
      return { tone: "amber", label: "Offline · Isolated AP" };
    case "awaiting_gateway":
      return { tone: "amber", label: "Awaiting Edge Gateway" };
    case "maintenance":
      return { tone: "rose", label: "Maintenance" };
    case "decommissioned":
      return { tone: "neutral", label: "Decommissioned" };
    default:
      return { tone: "neutral", label: "Registered (No Contact)" };
  }
}

export function DevicesView() {
  const { canOperate } = useAuth();
  const { capabilities, loading: sysLoading, refresh: refreshSystem } = useSystemState();
  const { notify } = useToast();

  const [devices, setDevices] = React.useState<DeviceRead[]>([]);
  const [fields, setFields] = React.useState<FieldRead[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [search, setSearch] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState("");

  // Modal state
  const [modalOpen, setModalOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<DeviceRead | null>(null);
  const [name, setName] = React.useState("");
  const [deviceIdentifier, setDeviceIdentifier] = React.useState("");
  const [deviceType, setDeviceType] = React.useState<DeviceType>("camera_module");
  const [hardwareModel, setHardwareModel] = React.useState("");
  const [assignedFieldId, setAssignedFieldId] = React.useState("");
  const [connectivityMode, setConnectivityMode] = React.useState<ConnectivityMode>("isolated_ap");
  const [statusVal, setStatusVal] = React.useState<DeviceStatus>("offline_isolated_ap");
  const [localSsid, setLocalSsid] = React.useState("");
  const [localDashboardUrl, setLocalDashboardUrl] = React.useState("");
  const [localStreamUrl, setLocalStreamUrl] = React.useState("");
  const [capLocalMjpeg, setCapLocalMjpeg] = React.useState(true);
  const [capRgbStill, setCapRgbStill] = React.useState(true);
  const [notes, setNotes] = React.useState("");
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const loadData = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [devRes, fieldRes] = await Promise.all([
        apiClient.listDevices({
          q: search.trim() || undefined,
          device_type: typeFilter || undefined,
          limit: 100,
        }),
        apiClient.listFields({ limit: 200 }),
      ]);
      setDevices(devRes.items);
      setTotal(devRes.total);
      setFields(fieldRes.items);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to query devices.");
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      void loadData();
    }, 150);
    return () => clearTimeout(timer);
  }, [loadData]);

  const fieldNameById = React.useMemo(() => {
    const map = new Map<string, string>();
    fields.forEach((f) => map.set(f.id, `${f.name} (${f.code})`));
    return map;
  }, [fields]);

  const applyEsp32Preset = () => {
    setName((prev) => prev || "AI Thinker ESP32-CAM Field Unit");
    setDeviceIdentifier((prev) => prev || "ESP32-CAM-OV2640-01");
    setDeviceType("camera_module");
    setHardwareModel("AI Thinker ESP32-CAM (OV2640)");
    setConnectivityMode("isolated_ap");
    setStatusVal("offline_isolated_ap");
    setLocalSsid("agroDrone");
    setLocalDashboardUrl("http://192.168.4.1");
    setLocalStreamUrl("http://192.168.4.1:81/stream");
    setCapLocalMjpeg(true);
    setCapRgbStill(true);
  };

  const openCreateModal = () => {
    setEditing(null);
    setName("");
    setDeviceIdentifier("");
    setDeviceType("camera_module");
    setHardwareModel("");
    setAssignedFieldId("");
    setConnectivityMode("isolated_ap");
    setStatusVal("offline_isolated_ap");
    setLocalSsid("");
    setLocalDashboardUrl("");
    setLocalStreamUrl("");
    setCapLocalMjpeg(false);
    setCapRgbStill(false);
    setNotes("");
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (device: DeviceRead) => {
    setEditing(device);
    setName(device.name);
    setDeviceIdentifier(device.device_identifier ?? "");
    setDeviceType((device.device_type as DeviceType) || "camera_module");
    setHardwareModel(device.hardware_model);
    setAssignedFieldId(device.assigned_field_id ?? "");
    setConnectivityMode((device.connectivity_mode as ConnectivityMode) || "isolated_ap");
    setStatusVal((device.status as DeviceStatus) || "offline_isolated_ap");
    setLocalSsid(device.local_ssid ?? String(device.connection_config.local_ssid ?? ""));
    setLocalDashboardUrl(
      device.local_endpoint_url ?? String(device.connection_config.local_dashboard_url ?? ""),
    );
    setLocalStreamUrl(String(device.connection_config.local_stream_url ?? ""));
    setCapLocalMjpeg(Boolean(device.capabilities.local_mjpeg));
    setCapRgbStill(Boolean(device.capabilities.rgb_still_capture));
    setNotes(device.notes ?? "");
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);

    if (name.trim().length < 2 || hardwareModel.trim().length < 2) {
      setFormError("Device name and hardware model are required.");
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(deviceIdentifier.trim())) {
      setFormError("Device identifier must start with a letter/digit and contain only A-Z, 0-9, ., _, -.");
      return;
    }

    const connection_config: Record<string, unknown> = {};
    if (localSsid.trim()) connection_config.local_ssid = localSsid.trim();
    if (localDashboardUrl.trim()) connection_config.local_dashboard_url = localDashboardUrl.trim();
    if (localStreamUrl.trim()) connection_config.local_stream_url = localStreamUrl.trim();

    // Always accurately mark unsupported telemetry features as false.
    const capabilitiesPayload: Record<string, unknown> = {
      local_mjpeg: capLocalMjpeg,
      rgb_still_capture: capRgbStill,
      gps: false,
      mavlink: false,
      battery_telemetry: false,
      multispectral_nir: false,
    };

    setSubmitting(true);
    try {
      if (editing) {
        await apiClient.updateDevice(editing.id, {
          name: name.trim(),
          device_type: deviceType,
          device_identifier: deviceIdentifier.trim(),
          hardware_model: hardwareModel.trim(),
          assigned_field_id: assignedFieldId || undefined,
          unassign_field: !assignedFieldId,
          connectivity_mode: connectivityMode,
          status: statusVal,
          local_ssid: localSsid.trim() || null,
          local_endpoint_url: localDashboardUrl.trim() || null,
          connection_config,
          capabilities: capabilitiesPayload,
          notes: notes.trim() || null,
        });
        notify({ tone: "success", title: "Device updated", description: `${name.trim()} saved.` });
      } else {
        await apiClient.createDevice({
          name: name.trim(),
          device_type: deviceType,
          device_identifier: deviceIdentifier.trim(),
          hardware_model: hardwareModel.trim(),
          assigned_field_id: assignedFieldId || null,
          connectivity_mode: connectivityMode,
          status: statusVal,
          local_ssid: localSsid.trim() || null,
          local_endpoint_url: localDashboardUrl.trim() || null,
          connection_config,
          capabilities: capabilitiesPayload,
          notes: notes.trim() || null,
        });
        notify({ tone: "success", title: "Device registered", description: `${name.trim()} added to inventory.` });
      }
      setModalOpen(false);
      await Promise.all([loadData(), refreshSystem()]);
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Failed to save device.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (device: DeviceRead) => {
    if (!window.confirm(`Remove device "${device.name}" (${device.device_identifier || device.id})?`)) {
      return;
    }
    try {
      await apiClient.deleteDevice(device.id);
      notify({ tone: "info", title: "Device deleted", description: `${device.name} removed.` });
      await Promise.all([loadData(), refreshSystem()]);
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: err instanceof ApiClientError ? err.message : "Unable to delete device.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Device Management"
        description="Register physical drone airframes, ESP32-CAM modules, and future Edge Gateways with honest connectivity tracking."
        phaseBadge="Phase 2 · Fleet Registry Active"
        phaseTone="emerald"
        actions={
          canOperate && (
            <Button variant="primary" size="sm" onClick={openCreateModal}>
              <Plus className="h-3.5 w-3.5" />
              <span>Register Device</span>
            </Button>
          )
        }
      />

      {/* Isolated AP Guardrail Banner */}
      <div className="flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3 text-xs text-amber-200/90">
        <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
        <p>
          <strong>Isolated AP Integrity:</strong> Devices are never marked &ldquo;online&rdquo; merely for existing
          in the database, and the backend never directly probes private IP{" "}
          <code className="font-mono text-amber-100">192.168.4.1</code>. Verified online presence activates with the
          Phase 4 outbound Field Edge Gateway.
        </p>
      </div>

      {/* Search & Filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-zinc-500" />
          <Input
            type="search"
            placeholder="Search by name, identifier, or model..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            aria-label="Search devices"
          />
        </div>
        <div className="flex items-center gap-2">
          <Select
            aria-label="Filter by device type"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="w-44"
          >
            <option value="">All Device Types</option>
            <option value="camera_module">Camera Module</option>
            <option value="airframe">Airframe</option>
            <option value="edge_gateway">Edge Gateway</option>
            <option value="sensor_node">Sensor Node</option>
          </Select>
          <Badge tone="neutral" className="font-mono">
            {total} Registered
          </Badge>
        </div>
      </div>

      {error && <FormError message={error} />}

      {/* Live DB Devices Table */}
      <Panel>
        <PanelHeader>
          <div>
            <PanelTitle>Persisted Device Registry</PanelTitle>
            <PanelDescription>
              Real hardware inventory stored in PostgreSQL / SQLite with ownership enforcement.
            </PanelDescription>
          </div>
        </PanelHeader>
        <PanelBody className="p-0">
          {loading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : devices.length === 0 ? (
            <div className="topo-grid flex min-h-[200px] flex-col items-center justify-center p-8 text-center">
              <Cpu className="h-5 w-5 text-emerald-400" />
              <p className="mt-3 text-sm font-medium text-zinc-100">No devices registered yet</p>
              <p className="mt-1 max-w-md text-xs text-zinc-400">
                Register your ESP32-CAM (OV2640) or E88 airframe to link hardware records to fields and missions.
              </p>
              {canOperate && (
                <Button variant="primary" size="sm" onClick={openCreateModal} className="mt-4">
                  <Plus className="h-3.5 w-3.5" />
                  <span>Register ESP32-CAM / Airframe</span>
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="px-5 py-3 font-semibold">Device & Identifier</th>
                    <th className="px-5 py-3 font-semibold">Assigned Field</th>
                    <th className="px-5 py-3 font-semibold">Connection Config</th>
                    <th className="px-5 py-3 font-semibold">Status</th>
                    <th className="px-5 py-3 font-semibold">Last Auth Contact</th>
                    <th className="px-5 py-3 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {devices.map((d) => {
                    const badge = deviceStatusBadge(d.status);
                    return (
                      <tr key={d.id} className="transition-colors hover:bg-white/[0.025]">
                        <td className="px-5 py-3.5">
                          <div className="font-medium text-zinc-100">{d.name}</div>
                          <div className="font-mono text-[11px] text-emerald-400">
                            {d.device_identifier || "—"} · {d.hardware_model}
                          </div>
                        </td>
                        <td className="px-5 py-3.5 text-zinc-300">
                          {d.assigned_field_id ? fieldNameById.get(d.assigned_field_id) ?? "Assigned" : "Unassigned"}
                        </td>
                        <td className="px-5 py-3.5 font-mono text-[11px] text-zinc-400">
                          <div>{d.connectivity_mode}</div>
                          {d.local_ssid && <div>SSID: {d.local_ssid}</div>}
                          {d.local_endpoint_url && <div className="text-zinc-500">{d.local_endpoint_url}</div>}
                        </td>
                        <td className="px-5 py-3.5">
                          <Badge tone={badge.tone}>{badge.label}</Badge>
                        </td>
                        <td className="px-5 py-3.5 font-mono text-[11px] text-zinc-500">
                          {d.last_authenticated_contact_at
                            ? new Date(d.last_authenticated_contact_at).toLocaleString()
                            : "Never (No Gateway)"}
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          {canOperate && (
                            <div className="inline-flex items-center gap-1">
                              <Button variant="ghost" size="sm" onClick={() => openEditModal(d)} title="Edit device">
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => void handleDelete(d)} title="Delete device">
                                <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PanelBody>
      </Panel>

      {/* Hardware Capability Baseline Matrix */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-tight text-zinc-100">
            Field Hardware Baseline & Honest Capability Matrix
          </h2>
          <Badge tone="muted" className="font-mono">
            Source: /api/v1/system/capabilities
          </Badge>
        </div>

        {sysLoading ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {[1, 2, 3, 4].map((n) => (
              <Skeleton key={n} className="h-52 w-full rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {(capabilities?.hardware_baseline ?? []).map((hw) => (
              <Panel key={hw.id}>
                <PanelHeader>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Cpu className="h-4 w-4 text-emerald-400" />
                      <PanelTitle>{hw.name}</PanelTitle>
                    </div>
                    <PanelDescription className="font-mono text-[11px]">
                      mode: {hw.connectivity_mode} · cloud_reachable: {String(hw.cloud_directly_reachable)}
                    </PanelDescription>
                  </div>
                  <Badge tone={hw.connectivity_mode === "isolated_ap" ? "amber" : "neutral"}>
                    {hw.category.replace("_", " ")}
                  </Badge>
                </PanelHeader>
                <PanelBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
                      Supported
                    </p>
                    <ul className="mt-2 space-y-1.5 text-xs text-zinc-300">
                      {hw.supported_capabilities.map((cap) => (
                        <li key={cap} className="flex items-start gap-2">
                          <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                          <span>{cap}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                      Not Supported (Never Simulated)
                    </p>
                    <ul className="mt-2 space-y-1.5 text-xs text-zinc-400">
                      {hw.unsupported_capabilities.map((cap) => (
                        <li key={cap} className="flex items-start gap-2">
                          <MinusCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-600" />
                          <span>{cap}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </PanelBody>
              </Panel>
            ))}
          </div>
        )}
      </div>

      {/* Register / Edit Device Modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? `Edit Device · ${editing.device_identifier || editing.name}` : "Register Field Device"}
        description="Record real hardware metadata without simulating online presence or probing local RFC-1918 networks."
        maxWidthClass="max-w-2xl"
      >
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {!editing && (
            <div className="flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-3.5 py-2.5">
              <span className="text-xs text-emerald-200">
                Using the AI Thinker ESP32-CAM (OV2640) on AP <code className="font-mono">agroDrone</code>?
              </span>
              <Button type="button" variant="subtle" size="sm" onClick={applyEsp32Preset}>
                Apply ESP32-CAM Preset
              </Button>
            </div>
          )}

          <FormError message={formError} />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="dev-name" required>
                Device Name
              </FieldLabel>
              <Input
                id="dev-name"
                placeholder="e.g., Field ESP32-CAM Unit #1"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <FieldLabel htmlFor="dev-id" required>
                Unique Device Identifier
              </FieldLabel>
              <Input
                id="dev-id"
                placeholder="e.g., ESP32-CAM-001"
                value={deviceIdentifier}
                onChange={(e) => setDeviceIdentifier(e.target.value)}
                required
              />
            </div>
            <div>
              <FieldLabel htmlFor="dev-type">Device Type</FieldLabel>
              <Select
                id="dev-type"
                value={deviceType}
                onChange={(e) => setDeviceType(e.target.value as DeviceType)}
              >
                <option value="camera_module">Camera Module</option>
                <option value="airframe">Drone Airframe</option>
                <option value="edge_gateway">Edge Gateway (Phase 4)</option>
                <option value="sensor_node">Sensor Node</option>
              </Select>
            </div>
            <div>
              <FieldLabel htmlFor="dev-model" required>
                Hardware Model
              </FieldLabel>
              <Input
                id="dev-model"
                placeholder="e.g., AI Thinker ESP32-CAM (OV2640)"
                value={hardwareModel}
                onChange={(e) => setHardwareModel(e.target.value)}
                required
              />
            </div>
            <div>
              <FieldLabel htmlFor="dev-field">Assigned Field (Optional)</FieldLabel>
              <Select
                id="dev-field"
                value={assignedFieldId}
                onChange={(e) => setAssignedFieldId(e.target.value)}
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
              <FieldLabel htmlFor="dev-status">Device Status</FieldLabel>
              <Select
                id="dev-status"
                value={statusVal}
                onChange={(e) => setStatusVal(e.target.value as DeviceStatus)}
              >
                <option value="offline_isolated_ap">Offline · Isolated AP</option>
                <option value="registered">Registered (No Authenticated Contact)</option>
                <option value="awaiting_gateway">Awaiting Field Edge Gateway</option>
                <option value="maintenance">Maintenance</option>
                <option value="decommissioned">Decommissioned</option>
              </Select>
            </div>
            <div>
              <FieldLabel htmlFor="dev-conn">Connectivity Mode</FieldLabel>
              <Select
                id="dev-conn"
                value={connectivityMode}
                onChange={(e) => setConnectivityMode(e.target.value as ConnectivityMode)}
              >
                <option value="isolated_ap">Isolated Wi-Fi AP (Local Only)</option>
                <option value="manual_import">Manual SD / Offline Import</option>
                <option value="edge_gateway">Future Field Edge Gateway (Phase 4)</option>
              </Select>
            </div>
            <div>
              <FieldLabel htmlFor="dev-ssid">Local Wi-Fi AP SSID</FieldLabel>
              <Input
                id="dev-ssid"
                placeholder="agroDrone"
                value={localSsid}
                onChange={(e) => setLocalSsid(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="dev-url">Local Dashboard URL (Metadata Only)</FieldLabel>
              <Input
                id="dev-url"
                placeholder="http://192.168.4.1"
                value={localDashboardUrl}
                onChange={(e) => setLocalDashboardUrl(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="dev-stream">Local MJPEG Stream URL (Metadata Only)</FieldLabel>
              <Input
                id="dev-stream"
                placeholder="http://192.168.4.1:81/stream"
                value={localStreamUrl}
                onChange={(e) => setLocalStreamUrl(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-4 rounded-lg border border-white/[0.07] bg-white/[0.02] p-3 text-xs text-zinc-300">
            <label className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={capLocalMjpeg}
                onChange={(e) => setCapLocalMjpeg(e.target.checked)}
                className="accent-emerald-500"
              />
              <span>Local MJPEG Stream</span>
            </label>
            <label className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={capRgbStill}
                onChange={(e) => setCapRgbStill(e.target.checked)}
                className="accent-emerald-500"
              />
              <span>RGB Still Capture</span>
            </label>
            <span className="text-[11px] text-zinc-500">
              (GPS, MAVLink, Battery Telemetry & NIR are fixed false for E88/OV2640 hardware)
            </span>
          </div>

          <div>
            <FieldLabel htmlFor="dev-notes">Hardware Notes</FieldLabel>
            <Textarea
              id="dev-notes"
              placeholder="Firmware build, lens focal notes, mounting bracket..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-white/[0.07] pt-4">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Saving..." : editing ? "Save Changes" : "Register Device"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

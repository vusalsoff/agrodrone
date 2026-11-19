"use client";

import * as React from "react";
import Link from "next/link";
import { Map, Pencil, Plus, Search, Sprout, Trash2 } from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { MapViewport } from "@/components/modules/map-viewport";
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
import type { FieldRead, GeoJsonPolygon } from "@/types/api";

export function FieldsView() {
  const { canManageFields } = useAuth();
  const { refresh: refreshSystem } = useSystemState();
  const { notify } = useToast();

  const [fields, setFields] = React.useState<FieldRead[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Filters
  const [search, setSearch] = React.useState("");
  const [boundaryFilter, setBoundaryFilter] = React.useState<"all" | "mapped" | "unmapped">("all");

  // Modal state
  const [modalOpen, setModalOpen] = React.useState(false);
  const [editingField, setEditingField] = React.useState<FieldRead | null>(null);
  const [name, setName] = React.useState("");
  const [code, setCode] = React.useState("");
  const [location, setLocation] = React.useState("");
  const [cropType, setCropType] = React.useState("");
  const [manualArea, setManualArea] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [polygon, setPolygon] = React.useState<GeoJsonPolygon | null>(null);
  const [polygonTouched, setPolygonTouched] = React.useState(false);
  const [polygonAreaHa, setPolygonAreaHa] = React.useState(0);
  const [polygonError, setPolygonError] = React.useState<string | null>(null);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const loadFields = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.listFields({
        q: search.trim() || undefined,
        has_boundary:
          boundaryFilter === "all" ? undefined : boundaryFilter === "mapped",
        limit: 100,
      });
      setFields(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load fields.");
    } finally {
      setLoading(false);
    }
  }, [search, boundaryFilter]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      void loadFields();
    }, 150);
    return () => clearTimeout(timer);
  }, [loadFields]);

  const openCreateModal = () => {
    setEditingField(null);
    setName("");
    setCode("");
    setLocation("");
    setCropType("");
    setManualArea("");
    setDescription("");
    setPolygon(null);
    setPolygonTouched(false);
    setPolygonAreaHa(0);
    setPolygonError(null);
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (field: FieldRead) => {
    setEditingField(field);
    setName(field.name);
    setCode(field.code);
    setLocation(field.location ?? "");
    setCropType(field.crop_type ?? "");
    setManualArea(field.area_hectares ? String(field.area_hectares) : "");
    setDescription(field.description ?? field.notes ?? "");
    setPolygon(field.boundary_geojson);
    setPolygonTouched(false);
    setPolygonAreaHa(field.area_hectares ?? 0);
    setPolygonError(null);
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);

    if (name.trim().length < 2) {
      setFormError("Field name must be at least 2 characters.");
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(code.trim())) {
      setFormError("Field code must start with a letter or number and use only letters, numbers, -, or _.");
      return;
    }
    if (polygonError) {
      setFormError(polygonError);
      return;
    }

    const parsedManualArea = manualArea.trim() ? Number(manualArea) : undefined;
    if (parsedManualArea !== undefined && (!Number.isFinite(parsedManualArea) || parsedManualArea <= 0)) {
      setFormError("Manual area must be a positive number in hectares.");
      return;
    }

    setSubmitting(true);
    try {
      if (editingField) {
        await apiClient.updateField(editingField.id, {
          name: name.trim(),
          code: code.trim().toUpperCase(),
          location: location.trim() || null,
          crop_type: cropType.trim() || null,
          description: description.trim() || null,
          area_hectares: polygon ? undefined : parsedManualArea,
          boundary_geojson: polygonTouched ? polygon : undefined,
          clear_boundary: polygonTouched && polygon === null,
        });
        notify({ tone: "success", title: "Field updated", description: `${name.trim()} saved.` });
      } else {
        await apiClient.createField({
          name: name.trim(),
          code: code.trim().toUpperCase(),
          location: location.trim() || null,
          crop_type: cropType.trim() || null,
          description: description.trim() || null,
          area_hectares: polygon ? undefined : parsedManualArea,
          boundary_geojson: polygon,
        });
        notify({ tone: "success", title: "Field created", description: `${name.trim()} registered.` });
      }
      setModalOpen(false);
      await Promise.all([loadFields(), refreshSystem()]);
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Failed to save field.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (field: FieldRead) => {
    if (!window.confirm(`Delete field "${field.name}" (${field.code})? Linked missions and devices will be unassigned.`)) {
      return;
    }
    try {
      await apiClient.deleteField(field.id);
      notify({ tone: "info", title: "Field deleted", description: `${field.name} removed.` });
      await Promise.all([loadFields(), refreshSystem()]);
    } catch (err) {
      notify({
        tone: "error",
        title: "Delete failed",
        description: err instanceof ApiClientError ? err.message : "Unable to delete field.",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Field Management"
        description="Manage agricultural parcels, crop classifications, and geodesic-validated GeoJSON boundaries."
        phaseBadge="Phase 2 · CRUD & GeoJSON Active"
        phaseTone="emerald"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href="/maps">
                <Map className="h-3.5 w-3.5" />
                <span>Open Map View</span>
              </Link>
            </Button>
            {canManageFields && (
              <Button variant="primary" size="sm" onClick={openCreateModal}>
                <Plus className="h-3.5 w-3.5" />
                <span>New Field</span>
              </Button>
            )}
          </div>
        }
      />

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-zinc-500" />
          <Input
            type="search"
            placeholder="Search by name, code, crop, or location..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            aria-label="Search fields"
          />
        </div>
        <div className="flex items-center gap-2">
          <Select
            aria-label="Filter by polygon boundary"
            value={boundaryFilter}
            onChange={(e) => setBoundaryFilter(e.target.value as "all" | "mapped" | "unmapped")}
            className="w-44"
          >
            <option value="all">All Parcels</option>
            <option value="mapped">With GeoJSON Polygon</option>
            <option value="unmapped">Without Polygon</option>
          </Select>
          <Badge tone="neutral" className="font-mono">
            {total} Total
          </Badge>
        </div>
      </div>

      {!canManageFields && (
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.025] px-4 py-3 text-xs text-zinc-400">
          Your role has read-only access to field definitions. Only <strong className="text-zinc-200">Admin</strong> and{" "}
          <strong className="text-zinc-200">Agronomist</strong> accounts can create, edit, or delete parcels.
        </div>
      )}

      {error && <FormError message={error} />}

      <Panel>
        <PanelHeader>
          <div>
            <PanelTitle>Agricultural Parcels</PanelTitle>
            <PanelDescription>
              Persisted in relational storage with ownership enforcement and WGS-84 geodesic measurement.
            </PanelDescription>
          </div>
        </PanelHeader>
        <PanelBody className="p-0">
          {loading ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : fields.length === 0 ? (
            <div className="topo-grid flex min-h-[240px] flex-col items-center justify-center p-8 text-center">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/[0.09] bg-white/[0.03]">
                <Sprout className="h-5 w-5 text-emerald-400" />
              </div>
              <h3 className="mt-4 text-sm font-semibold text-zinc-100">No fields found</h3>
              <p className="mt-1.5 max-w-md text-xs text-zinc-400">
                {search || boundaryFilter !== "all"
                  ? "No parcels match the active search or boundary filters."
                  : "Register your first agricultural field and optionally plot its exact GeoJSON polygon on the map."}
              </p>
              {canManageFields && !search && boundaryFilter === "all" && (
                <Button variant="primary" size="sm" onClick={openCreateModal} className="mt-4">
                  <Plus className="h-3.5 w-3.5" />
                  <span>Register First Field</span>
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="px-5 py-3 font-semibold">Field / Code</th>
                    <th className="px-5 py-3 font-semibold">Location & Crop</th>
                    <th className="px-5 py-3 font-semibold">Area (ha)</th>
                    <th className="px-5 py-3 font-semibold">Boundary</th>
                    <th className="px-5 py-3 font-semibold">Created</th>
                    <th className="px-5 py-3 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {fields.map((field) => (
                    <tr key={field.id} className="transition-colors hover:bg-white/[0.025]">
                      <td className="px-5 py-3.5">
                        <div className="font-medium text-zinc-100">{field.name}</div>
                        <div className="font-mono text-[11px] text-emerald-400">{field.code}</div>
                      </td>
                      <td className="px-5 py-3.5 text-zinc-300">
                        <div>{field.location || "—"}</div>
                        <div className="text-[11px] text-zinc-500">{field.crop_type || "Crop not set"}</div>
                      </td>
                      <td className="px-5 py-3.5 font-mono text-zinc-200 tabular-nums">
                        {field.area_hectares !== null ? `${field.area_hectares.toFixed(4)} ha` : "—"}
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge tone={field.boundary_geojson ? "emerald" : "muted"}>
                          {field.boundary_geojson ? "GeoJSON Mapped" : "No Polygon"}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-zinc-400">
                        {new Date(field.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          <Button variant="ghost" size="sm" asChild title="Inspect on Map">
                            <Link href="/maps">
                              <Map className="h-3.5 w-3.5" />
                            </Link>
                          </Button>
                          {canManageFields && (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openEditModal(field)}
                                title="Edit field"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => void handleDelete(field)}
                                title="Delete field"
                              >
                                <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                              </Button>
                            </>
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

      {/* Create / Edit Field Modal with Live MapLibre GeoJSON Drawer */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingField ? `Edit Field · ${editingField.code}` : "Register Agricultural Field"}
        description="Draw an optional GeoJSON boundary on the map for automatic WGS-84 geodesic hectare calculation."
        maxWidthClass="max-w-3xl"
      >
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <FormError message={formError} />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="field-name" required>
                Field Name
              </FieldLabel>
              <Input
                id="field-name"
                placeholder="e.g., North Orchard Parcel A"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <FieldLabel htmlFor="field-code" required>
                Parcel Code
              </FieldLabel>
              <Input
                id="field-code"
                placeholder="e.g., NO-A01"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                required
              />
            </div>
            <div>
              <FieldLabel htmlFor="field-location">Location / Region</FieldLabel>
              <Input
                id="field-location"
                placeholder="e.g., Ganja Foothills"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="field-crop">Crop Type</FieldLabel>
              <Input
                id="field-crop"
                placeholder="e.g., Winter Wheat, Grapes, Orchards"
                value={cropType}
                onChange={(e) => setCropType(e.target.value)}
              />
            </div>
          </div>

          <div>
            <FieldLabel htmlFor="field-desc">Description</FieldLabel>
            <Textarea
              id="field-desc"
              placeholder="Soil type, irrigation layout, slope notes..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {!polygon && (
            <div className="max-w-xs">
              <FieldLabel htmlFor="field-manual-area">Manual Area (Hectares, optional)</FieldLabel>
              <Input
                id="field-manual-area"
                type="number"
                step="0.0001"
                min="0.0001"
                placeholder="Auto-calculated if polygon drawn"
                value={manualArea}
                onChange={(e) => setManualArea(e.target.value)}
              />
            </div>
          )}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <FieldLabel>Geographic Boundary (Interactive MapLibre GeoJSON Polygon)</FieldLabel>
              {polygon && !polygonError && (
                <Badge tone="emerald" className="font-mono">
                  Geodesic Area: {polygonAreaHa.toFixed(4)} ha
                </Badge>
              )}
            </div>
            <MapViewport
              editable
              fields={fields}
              selectedFieldId={editingField?.id ?? null}
              editingPolygon={editingField?.boundary_geojson ?? null}
              onChangePolygon={(poly, area, err) => {
                setPolygonTouched(true);
                setPolygon(poly);
                setPolygonAreaHa(area);
                setPolygonError(err);
              }}
              heightClass="h-[320px]"
            />
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-white/[0.07] pt-4">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting || Boolean(polygonError)}>
              {submitting ? "Saving..." : editingField ? "Save Changes" : "Create Field"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

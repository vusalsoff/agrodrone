"use client";

import * as React from "react";
import Link from "next/link";
import { Compass, Info, MapPin, Pencil, Save, Sprout, Trash2, X } from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { MapViewport } from "@/components/modules/map-viewport";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";
import type { FieldRead, GeoJsonPolygon, MapAnalyticsResponse } from "@/types/api";

export function MapsView() {
  const { canManageFields } = useAuth();
  const { notify } = useToast();

  const [fields, setFields] = React.useState<FieldRead[]>([]);
  const [mapAnalytics, setMapAnalytics] = React.useState<MapAnalyticsResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const [editingMode, setEditingMode] = React.useState(false);
  const [draftPolygon, setDraftPolygon] = React.useState<GeoJsonPolygon | null>(null);
  const [draftArea, setDraftArea] = React.useState<number>(0);
  const [draftError, setDraftError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const loadFields = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [res, analyticsRes] = await Promise.all([
        apiClient.listFields({ limit: 200 }),
        apiClient.getMapAnalytics().catch(() => null),
      ]);
      setFields(res.items);
      if (analyticsRes) setMapAnalytics(analyticsRes);
      if (res.items.length > 0 && !selectedId) {
        setSelectedId(res.items[0].id);
      }
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load field parcels.");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  React.useEffect(() => {
    void loadFields();
  }, [loadFields]);

  const selectedField = React.useMemo(
    () => fields.find((f) => f.id === selectedId) ?? null,
    [fields, selectedId],
  );

  const startEditing = () => {
    if (!selectedField) return;
    setDraftPolygon(selectedField.boundary_geojson);
    setDraftArea(selectedField.area_hectares ?? 0);
    setDraftError(null);
    setEditingMode(true);
  };

  const cancelEditing = () => {
    setEditingMode(false);
    setDraftError(null);
  };

  const saveBoundary = async () => {
    if (!selectedField) return;
    if (draftError) {
      notify({ tone: "error", title: "Invalid polygon", description: draftError });
      return;
    }
    setSaving(true);
    try {
      const updated = await apiClient.updateField(
        selectedField.id,
        draftPolygon
          ? { boundary_geojson: draftPolygon }
          : { clear_boundary: true },
      );
      setFields((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      setEditingMode(false);
      notify({
        tone: "success",
        title: draftPolygon ? "Boundary saved" : "Boundary removed",
        description: draftPolygon
          ? `${updated.name} measured at ${updated.area_hectares?.toFixed(4)} ha.`
          : `Cleared GeoJSON boundary for ${updated.name}.`,
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Failed to save boundary",
        description: err instanceof ApiClientError ? err.message : "Server rejected polygon.",
      });
    } finally {
      setSaving(false);
    }
  };

  const removeBoundary = async () => {
    if (!selectedField || !selectedField.boundary_geojson) return;
    setSaving(true);
    try {
      const updated = await apiClient.updateField(selectedField.id, { clear_boundary: true });
      setFields((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      setEditingMode(false);
      notify({ tone: "info", title: "Polygon deleted", description: `Cleared boundary for ${updated.name}.` });
    } catch (err) {
      notify({
        tone: "error",
        title: "Unable to delete polygon",
        description: err instanceof ApiClientError ? err.message : "Error clearing boundary.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Interactive Field Maps"
        description="Draw, edit, validate, and measure agricultural parcel polygons with WGS-84 geodesic area calculations."
        phaseBadge="Phase 2 · Interactive GeoJSON Active"
        phaseTone="emerald"
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link href="/fields">
              <Sprout className="h-3.5 w-3.5" />
              <span>Manage Fields</span>
            </Link>
          </Button>
        }
      />

      {error && (
        <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/[0.08] p-4 text-xs text-rose-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <MapViewport
            fields={fields}
            selectedFieldId={selectedId}
            onSelectField={(f) => {
              if (!editingMode) setSelectedId(f.id);
            }}
            editable={editingMode}
            editingPolygon={editingMode ? selectedField?.boundary_geojson ?? null : null}
            onChangePolygon={(poly, area, err) => {
              setDraftPolygon(poly);
              setDraftArea(area);
              setDraftError(err);
            }}
            heightClass="h-[540px]"
          />
        </div>

        <div className="space-y-4 lg:col-span-4">
          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Saved Field Parcels</PanelTitle>
                <PanelDescription>Select a field to inspect or draw/edit its polygon.</PanelDescription>
              </div>
              <Badge tone="emerald" className="font-mono">
                {fields.length} Total
              </Badge>
            </PanelHeader>
            <PanelBody className="space-y-2.5">
              {loading ? (
                <div className="space-y-2">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : fields.length === 0 ? (
                <div className="rounded-lg border border-dashed border-white/[0.10] p-5 text-center">
                  <p className="text-xs font-medium text-zinc-200">No fields registered yet</p>
                  <p className="mt-1 text-[11px] text-zinc-400">
                    Create your first agricultural field parcel to draw and measure its boundary.
                  </p>
                  {canManageFields && (
                    <Button variant="primary" size="sm" asChild className="mt-3">
                      <Link href="/fields">Create Field</Link>
                    </Button>
                  )}
                </div>
              ) : (
                <div className="max-h-[220px] space-y-1.5 overflow-y-auto pr-1">
                  {fields.map((field) => {
                    const isSelected = field.id === selectedId;
                    return (
                      <button
                        key={field.id}
                        type="button"
                        disabled={editingMode}
                        onClick={() => setSelectedId(field.id)}
                        className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-left text-xs transition-colors ${
                          isSelected
                            ? "border-emerald-500/35 bg-emerald-500/[0.10] text-zinc-50"
                            : "border-white/[0.06] bg-white/[0.02] text-zinc-300 hover:bg-white/[0.05]"
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium">{field.name}</div>
                          <div className="font-mono text-[10px] text-zinc-400">
                            {field.code} · {field.area_hectares ? `${field.area_hectares.toFixed(2)} ha` : "Unmeasured"}
                          </div>
                        </div>
                        <Badge tone={field.boundary_geojson ? "emerald" : "muted"}>
                          {field.boundary_geojson ? "Mapped" : "No Poly"}
                        </Badge>
                      </button>
                    );
                  })}
                </div>
              )}

              {selectedField && (
                <div className="space-y-3 border-t border-white/[0.07] pt-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-zinc-100">{selectedField.name}</p>
                      <p className="font-mono text-[11px] text-zinc-400">
                        {selectedField.code} · {selectedField.crop_type || "Crop unspecified"}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="rounded-lg bg-white/[0.025] p-2.5">
                      <span className="text-zinc-500">Area</span>
                      <p className="mt-0.5 font-mono text-emerald-300">
                        {editingMode && draftPolygon
                          ? `${draftArea.toFixed(4)} ha`
                          : selectedField.area_hectares
                            ? `${selectedField.area_hectares.toFixed(4)} ha`
                            : "—"}
                      </p>
                    </div>
                    <div className="rounded-lg bg-white/[0.025] p-2.5">
                      <span className="text-zinc-500">Centroid</span>
                      <p className="mt-0.5 truncate font-mono text-zinc-200">
                        {selectedField.centroid_lat !== null && selectedField.centroid_lng !== null
                          ? `${selectedField.centroid_lat.toFixed(4)}, ${selectedField.centroid_lng.toFixed(4)}`
                          : "—"}
                      </p>
                    </div>
                  </div>

                  {canManageFields && (
                    <div className="flex flex-wrap gap-2">
                      {editingMode ? (
                        <>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => void saveBoundary()}
                            disabled={saving || Boolean(draftError)}
                            className="flex-1"
                          >
                            <Save className="h-3.5 w-3.5" />
                            <span>{saving ? "Saving..." : "Save Boundary"}</span>
                          </Button>
                          <Button variant="ghost" size="sm" onClick={cancelEditing} disabled={saving}>
                            <X className="h-3.5 w-3.5" />
                            <span>Cancel</span>
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button variant="subtle" size="sm" onClick={startEditing} className="flex-1">
                            <Pencil className="h-3.5 w-3.5" />
                            <span>
                              {selectedField.boundary_geojson ? "Edit Polygon" : "Draw Polygon"}
                            </span>
                          </Button>
                          {selectedField.boundary_geojson && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => void removeBoundary()}
                              disabled={saving}
                              title="Delete polygon boundary"
                            >
                              <Trash2 className="h-3.5 w-3.5 text-rose-400" />
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {(() => {
                    const fs = mapAnalytics?.fields.find((f) => f.field_id === selectedField.id);
                    if (!fs) return null;
                    return (
                      <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 text-xs">
                        <p className="mb-1.5 font-medium text-zinc-200">Field Analytics Summary</p>
                        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                          <span className="text-zinc-400">Missions: {fs.missions_count}</span>
                          <span className="text-zinc-400">AI Jobs: {fs.jobs_count}</span>
                          <span className="text-zinc-400">
                            Unique Class Hits: {fs.unique_job_class_occurrences}
                          </span>
                          <span className="text-emerald-300">
                            Confirmed: {fs.confirmed_detections}
                          </span>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </PanelBody>
          </Panel>

          {mapAnalytics ? (
            <Panel>
              <PanelHeader>
                <PanelTitle className="text-sm">Verified Geotagged Points</PanelTitle>
              </PanelHeader>
              <PanelBody className="space-y-2 text-xs">
                <p className="text-[11px] text-amber-200/90">{mapAnalytics.gps_honesty_note}</p>
                {mapAnalytics.verified_detection_points.length === 0 ? (
                  <p className="text-zinc-500">
                    No media assets with verified EXIF or operator GPS coordinates.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {mapAnalytics.verified_detection_points.map((pt) => (
                      <li
                        key={pt.media_asset_id}
                        className="rounded border border-white/[0.08] bg-white/[0.02] p-2 font-mono text-[11px] text-zinc-300"
                      >
                        {pt.original_filename} ({pt.geo_source}) · {pt.geo_lat.toFixed(4)},{" "}
                        {pt.geo_lng.toFixed(4)} · {pt.detection_count} detections
                      </li>
                    ))}
                  </ul>
                )}
              </PanelBody>
            </Panel>
          ) : null}

          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Sensor & Geotag Honesty</PanelTitle>
              </div>
              <Info className="h-4 w-4 text-amber-400" />
            </PanelHeader>
            <PanelBody className="space-y-2.5 text-xs leading-relaxed text-zinc-400">
              <div className="flex items-start gap-2">
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                <p>
                  Coordinates are strictly user-drawn or operator-supplied — AgroDrone never invents
                  field boundaries or fake drone GPS tracks.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <Compass className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                <p>
                  OV2640 captures visible RGB light only (not multispectral NIR NDVI).
                </p>
              </div>
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}

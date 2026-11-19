"use client";

import * as React from "react";
import type { Map as MapLibreMap, Marker, StyleSpecification } from "maplibre-gl";
import {
  Crosshair,
  Globe,
  Layers,
  Pencil,
  RotateCcw,
  Trash2,
  Undo2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { appEnv } from "@/lib/env";
import {
  computePolygonAreaHectares,
  getPolygonBounds,
  polygonToEditableVertices,
  validateEditableVertices,
  verticesToClosedPolygon,
} from "@/lib/geo";
import type { FieldRead, GeoJsonPolygon } from "@/types/api";

type BasemapMode = "graticule" | "satellite";

function buildDarkGraticuleStyle(): StyleSpecification {
  const features: Array<{
    type: "Feature";
    properties: Record<string, unknown>;
    geometry: { type: "LineString"; coordinates: number[][] };
  }> = [];

  for (let lng = -180; lng <= 180; lng += 10) {
    features.push({
      type: "Feature",
      properties: { kind: lng === 0 ? "axis" : "grid" },
      geometry: {
        type: "LineString",
        coordinates: [
          [lng, -80],
          [lng, 80],
        ],
      },
    });
  }

  for (let lat = -70; lat <= 70; lat += 10) {
    features.push({
      type: "Feature",
      properties: { kind: lat === 0 ? "axis" : "grid" },
      geometry: {
        type: "LineString",
        coordinates: [
          [-180, lat],
          [180, lat],
        ],
      },
    });
  }

  return {
    version: 8,
    name: "AgroDrone Dark Vector Graticule",
    sources: {
      graticule: {
        type: "geojson",
        data: { type: "FeatureCollection", features },
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#090D0B" } },
      {
        id: "graticule-grid",
        type: "line",
        source: "graticule",
        filter: ["==", ["get", "kind"], "grid"],
        paint: { "line-color": "rgba(148, 163, 155, 0.13)", "line-width": 1 },
      },
      {
        id: "graticule-axis",
        type: "line",
        source: "graticule",
        filter: ["==", ["get", "kind"], "axis"],
        paint: { "line-color": "rgba(16, 185, 129, 0.32)", "line-width": 1.25 },
      },
    ],
  };
}

function buildSatelliteStyle(): StyleSpecification {
  return {
    version: 8,
    name: "AgroDrone Satellite Imagery",
    sources: {
      esri_imagery: {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        attribution: "Esri World Imagery",
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#090D0B" } },
      {
        id: "esri-imagery-layer",
        type: "raster",
        source: "esri_imagery",
        paint: { "raster-brightness-max": 0.92, "raster-saturation": -0.05 },
      },
    ],
  };
}

export interface MapViewportProps {
  fields?: FieldRead[];
  selectedFieldId?: string | null;
  onSelectField?: (field: FieldRead) => void;
  editable?: boolean;
  editingPolygon?: GeoJsonPolygon | null;
  onChangePolygon?: (polygon: GeoJsonPolygon | null, areaHectares: number, validationError: string | null) => void;
  heightClass?: string;
}

const SAVED_SOURCE_ID = "agrodrone-saved-fields";
const DRAFT_SOURCE_ID = "agrodrone-draft-polygon";

export function MapViewport({
  fields = [],
  selectedFieldId = null,
  onSelectField,
  editable = false,
  editingPolygon = null,
  onChangePolygon,
  heightClass = "h-[460px]",
}: MapViewportProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<MapLibreMap | null>(null);
  const maplibreglRef = React.useRef<typeof import("maplibre-gl") | null>(null);
  const markersRef = React.useRef<Marker[]>([]);

  const [basemap, setBasemap] = React.useState<BasemapMode>("graticule");
  const [mapReady, setMapReady] = React.useState(false);
  const [styleRevision, setStyleRevision] = React.useState(0);
  const [webglError, setWebglError] = React.useState<string | null>(null);
  const [drawingMode, setDrawingMode] = React.useState<boolean>(editable);
  const [vertices, setVertices] = React.useState<[number, number][]>(() =>
    polygonToEditableVertices(editingPolygon),
  );
  const [jumpLng, setJumpLng] = React.useState("");
  const [jumpLat, setJumpLat] = React.useState("");
  const [cursor, setCursor] = React.useState<{ lng: number; lat: number; zoom: number }>({
    lng: 0,
    lat: 20,
    zoom: 1.8,
  });

  // Sync incoming editingPolygon when prop changes externally (e.g. switching selected field).
  const polygonSignature = React.useMemo(
    () => (editingPolygon ? JSON.stringify(editingPolygon.coordinates) : ""),
    [editingPolygon],
  );

  React.useEffect(() => {
    setVertices(polygonToEditableVertices(editingPolygon));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polygonSignature]);

  React.useEffect(() => {
    setDrawingMode(editable);
  }, [editable]);

  const draftPolygon = React.useMemo(() => verticesToClosedPolygon(vertices), [vertices]);
  const draftValidationError = React.useMemo(
    () => (vertices.length === 0 ? null : validateEditableVertices(vertices)),
    [vertices],
  );
  const draftAreaHa = React.useMemo(
    () => (draftPolygon && !draftValidationError ? computePolygonAreaHectares(draftPolygon) : 0),
    [draftPolygon, draftValidationError],
  );

  const onChangeRef = React.useRef(onChangePolygon);
  const drawingModeRef = React.useRef(drawingMode);
  const verticesRef = React.useRef(vertices);
  const fieldsRef = React.useRef(fields);
  const onSelectFieldRef = React.useRef(onSelectField);

  React.useEffect(() => {
    onChangeRef.current = onChangePolygon;
    drawingModeRef.current = drawingMode;
    verticesRef.current = vertices;
    fieldsRef.current = fields;
    onSelectFieldRef.current = onSelectField;
  }, [onChangePolygon, drawingMode, vertices, fields, onSelectField]);

  const emitVertices = React.useCallback((nextVertices: [number, number][]) => {
    setVertices(nextVertices);
    if (!onChangeRef.current) return;
    if (nextVertices.length === 0) {
      onChangeRef.current(null, 0, null);
      return;
    }
    const validationErr = validateEditableVertices(nextVertices);
    const poly = verticesToClosedPolygon(nextVertices);
    const area = poly && !validationErr ? computePolygonAreaHectares(poly) : 0;
    onChangeRef.current(validationErr ? null : poly, area, validationErr);
  }, []);

  // Ensure custom GeoJSON sources & layers exist after initial load or style switch.
  const ensureOverlayLayers = React.useCallback((map: MapLibreMap) => {
    if (!map.getSource(SAVED_SOURCE_ID)) {
      map.addSource(SAVED_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "saved-fields-fill",
        type: "fill",
        source: SAVED_SOURCE_ID,
        paint: {
          "fill-color": [
            "case",
            ["boolean", ["get", "selected"], false],
            "rgba(52, 211, 153, 0.32)",
            "rgba(16, 185, 129, 0.18)",
          ],
          "fill-opacity": 1,
        },
      });
      map.addLayer({
        id: "saved-fields-outline",
        type: "line",
        source: SAVED_SOURCE_ID,
        paint: {
          "line-color": [
            "case",
            ["boolean", ["get", "selected"], false],
            "#34D399",
            "rgba(52, 211, 153, 0.75)",
          ],
          "line-width": ["case", ["boolean", ["get", "selected"], false], 2.5, 1.5],
        },
      });
    }

    if (!map.getSource(DRAFT_SOURCE_ID)) {
      map.addSource(DRAFT_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "draft-poly-fill",
        type: "fill",
        source: DRAFT_SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": "rgba(16, 185, 129, 0.28)",
        },
      });
      map.addLayer({
        id: "draft-poly-line",
        type: "line",
        source: DRAFT_SOURCE_ID,
        paint: {
          "line-color": "#34D399",
          "line-width": 2,
          "line-dasharray": [3, 2],
        },
      });
    }
  }, []);

  // Initialize MapLibre map once
  React.useEffect(() => {
    let active = true;

    async function initMap() {
      if (!containerRef.current) return;
      try {
        const maplibregl = await import("maplibre-gl");
        if (!active || !containerRef.current) return;
        maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
        maplibreglRef.current = maplibregl;

        const map = new maplibregl.Map({
          container: containerRef.current,
          style: appEnv.mapStyleUrl || buildDarkGraticuleStyle(),
          center: [0, 20],
          zoom: 1.8,
          attributionControl: false,
        });

        map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
        map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

        map.on("load", () => {
          if (!active) return;
          ensureOverlayLayers(map);
          setMapReady(true);
          setStyleRevision((r) => r + 1);

          // Fit cleanly to existing saved fields if any exist (never inventing coordinates).
          const existingPolys = fieldsRef.current
            .map((f) => f.boundary_geojson)
            .filter((p): p is GeoJsonPolygon => Boolean(p));
          if (editingPolygon) {
            existingPolys.push(editingPolygon);
          }
          const bounds = getPolygonBounds(existingPolys);
          if (bounds) {
            map.fitBounds(bounds, { padding: 56, maxZoom: 15, duration: 0 });
          }
        });

        map.on("mousemove", (evt) => {
          if (!active) return;
          setCursor({ lng: evt.lngLat.lng, lat: evt.lngLat.lat, zoom: map.getZoom() });
        });

        map.on("zoom", () => {
          if (!active) return;
          setCursor((prev) => ({ ...prev, zoom: map.getZoom() }));
        });

        map.on("click", (evt) => {
          if (!active) return;
          if (drawingModeRef.current) {
            const nextPt: [number, number] = [
              Math.round(evt.lngLat.lng * 1e7) / 1e7,
              Math.round(evt.lngLat.lat * 1e7) / 1e7,
            ];
            emitVertices([...verticesRef.current, nextPt]);
            return;
          }

          if (map.getLayer("saved-fields-fill") && onSelectFieldRef.current) {
            const hits = map.queryRenderedFeatures(evt.point, {
              layers: ["saved-fields-fill"],
            });
            const hitId = hits[0]?.properties?.id;
            if (typeof hitId === "string") {
              const matched = fieldsRef.current.find((f) => f.id === hitId);
              if (matched) onSelectFieldRef.current(matched);
            }
          }
        });

        mapRef.current = map;
      } catch (err) {
        if (active) {
          setWebglError(
            err instanceof Error
              ? err.message
              : "WebGL context unavailable in this browser environment.",
          );
        }
      }
    }

    void initMap();

    return () => {
      active = false;
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle basemap switch cleanly
  const switchBasemap = (nextMode: BasemapMode) => {
    setBasemap(nextMode);
    const map = mapRef.current;
    if (!map) return;
    const style =
      nextMode === "satellite"
        ? buildSatelliteStyle()
        : appEnv.mapStyleUrl || buildDarkGraticuleStyle();
    map.once("style.load", () => {
      ensureOverlayLayers(map);
      setStyleRevision((r) => r + 1);
    });
    map.setStyle(style);
  };

  // Sync saved field polygons to MapLibre GeoJSON source
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    ensureOverlayLayers(map);

    const source = map.getSource(SAVED_SOURCE_ID) as
      | { setData: (data: GeoJSON.FeatureCollection) => void }
      | undefined;
    if (!source) return;

    const features: GeoJSON.Feature[] = fields
      .filter((f) => f.boundary_geojson && f.id !== (editable ? selectedFieldId : "__none__"))
      .map((f) => ({
        type: "Feature",
        properties: {
          id: f.id,
          name: f.name,
          code: f.code,
          selected: f.id === selectedFieldId,
        },
        geometry: f.boundary_geojson as GeoJSON.Polygon,
      }));

    source.setData({ type: "FeatureCollection", features });
  }, [fields, selectedFieldId, editable, mapReady, styleRevision, ensureOverlayLayers]);

  // Sync editable draft polygon & draggable vertex markers
  React.useEffect(() => {
    const map = mapRef.current;
    const maplibregl = maplibreglRef.current;
    if (!map || !maplibregl || !mapReady) return;
    ensureOverlayLayers(map);

    const source = map.getSource(DRAFT_SOURCE_ID) as
      | { setData: (data: GeoJSON.FeatureCollection) => void }
      | undefined;

    const draftFeatures: GeoJSON.Feature[] = [];
    if (vertices.length >= 2) {
      draftFeatures.push({
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates:
            vertices.length >= 3 ? [...vertices, vertices[0]] : vertices,
        },
      });
    }
    if (draftPolygon) {
      draftFeatures.push({
        type: "Feature",
        properties: {},
        geometry: draftPolygon as GeoJSON.Polygon,
      });
    }
    source?.setData({ type: "FeatureCollection", features: draftFeatures });

    // Rebuild draggable vertex markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    if (editable || drawingMode) {
      vertices.forEach((pt, idx) => {
        const el = document.createElement("button");
        el.type = "button";
        el.setAttribute("aria-label", `Vertex ${idx + 1}. Drag to move or right-click to remove.`);
        el.title = `Vertex ${idx + 1} (drag to move, right-click to remove)`;
        el.className =
          "h-3.5 w-3.5 rounded-full border-2 border-zinc-950 bg-emerald-400 shadow-[0_0_0_2px_rgba(16,185,129,0.35)] cursor-grab active:cursor-grabbing";

        el.addEventListener("contextmenu", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const updated = verticesRef.current.filter((_, i) => i !== idx);
          emitVertices(updated);
        });

        const marker = new maplibregl.Marker({ element: el, draggable: true })
          .setLngLat(pt)
          .addTo(map);

        marker.on("dragend", () => {
          const pos = marker.getLngLat();
          const updated = verticesRef.current.map((v, i) =>
            i === idx
              ? ([
                  Math.round(pos.lng * 1e7) / 1e7,
                  Math.round(pos.lat * 1e7) / 1e7,
                ] as [number, number])
              : v,
          );
          emitVertices(updated);
        });

        markersRef.current.push(marker);
      });
    }
  }, [vertices, draftPolygon, editable, drawingMode, mapReady, styleRevision, emitVertices, ensureOverlayLayers]);

  // Fit bounds when selectedFieldId changes
  const focusSelected = React.useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const targetPolys: GeoJsonPolygon[] = [];
    const selected = fields.find((f) => f.id === selectedFieldId);
    if (selected?.boundary_geojson) {
      targetPolys.push(selected.boundary_geojson);
    } else if (draftPolygon) {
      targetPolys.push(draftPolygon);
    } else {
      fields.forEach((f) => {
        if (f.boundary_geojson) targetPolys.push(f.boundary_geojson);
      });
    }
    const bounds = getPolygonBounds(targetPolys);
    if (bounds) {
      map.fitBounds(bounds, { padding: 60, maxZoom: 15, duration: 500 });
    }
  }, [fields, selectedFieldId, draftPolygon]);

  const handleJumpToCoords = () => {
    const lng = Number(jumpLng);
    const lat = Number(jumpLat);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    if (lng < -180 || lng > 180 || lat < -90 || lat > 90) return;
    mapRef.current?.flyTo({ center: [lng, lat], zoom: 14, duration: 600 });
  };

  const handleJumpKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      handleJumpToCoords();
    }
  };

  if (webglError) {
    return (
      <div
        className={`topo-grid flex ${heightClass} flex-col items-center justify-center rounded-xl border border-white/[0.08] bg-[#090D0B] p-6 text-center`}
      >
        <p className="text-sm font-medium text-zinc-200">MapLibre GL WebGL Fallback</p>
        <p className="mt-1.5 max-w-md text-xs text-zinc-400">{webglError}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {/* Compact Map Controls Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/[0.07] bg-[#0C110F] px-3 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            type="button"
            variant={basemap === "graticule" ? "subtle" : "ghost"}
            size="sm"
            onClick={() => switchBasemap("graticule")}
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Vector Grid</span>
          </Button>
          <Button
            type="button"
            variant={basemap === "satellite" ? "subtle" : "ghost"}
            size="sm"
            onClick={() => switchBasemap("satellite")}
          >
            <Globe className="h-3.5 w-3.5" />
            <span>Satellite</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={focusSelected}
            disabled={!draftPolygon && !fields.some((f) => f.boundary_geojson)}
            title="Fit map to saved field boundaries"
          >
            <Crosshair className="h-3.5 w-3.5" />
            <span>Fit Fields</span>
          </Button>
        </div>

        {/* Manual coordinate jump (never invents default coordinates) */}
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            step="any"
            placeholder="Lat"
            aria-label="Jump latitude"
            value={jumpLat}
            onChange={(e) => setJumpLat(e.target.value)}
            onKeyDown={handleJumpKeyDown}
            className="h-7 w-20 rounded-md border border-white/[0.10] bg-[#080B0A] px-2 font-mono text-[11px] text-zinc-200 placeholder:text-zinc-600"
          />
          <input
            type="number"
            step="any"
            placeholder="Lng"
            aria-label="Jump longitude"
            value={jumpLng}
            onChange={(e) => setJumpLng(e.target.value)}
            onKeyDown={handleJumpKeyDown}
            className="h-7 w-20 rounded-md border border-white/[0.10] bg-[#080B0A] px-2 font-mono text-[11px] text-zinc-200 placeholder:text-zinc-600"
          />
          <Button type="button" variant="secondary" size="sm" className="h-7 px-2 text-[11px]" onClick={handleJumpToCoords}>
            Go
          </Button>
        </div>

        {editable && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              type="button"
              variant={drawingMode ? "primary" : "outline"}
              size="sm"
              onClick={() => setDrawingMode((prev) => !prev)}
            >
              <Pencil className="h-3.5 w-3.5" />
              <span>{drawingMode ? "Click Map to Plot" : "Resume Drawing"}</span>
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={vertices.length === 0}
              onClick={() => emitVertices(vertices.slice(0, -1))}
              title="Undo last vertex"
            >
              <Undo2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={vertices.length === 0}
              onClick={() => emitVertices([])}
              title="Clear polygon"
            >
              <Trash2 className="h-3.5 w-3.5 text-rose-400" />
            </Button>
            {editingPolygon && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => emitVertices(polygonToEditableVertices(editingPolygon))}
                title="Reset to saved boundary"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        )}
      </div>

      {/* MapLibre Canvas */}
      <div
        className={`relative ${heightClass} w-full overflow-hidden rounded-xl border border-white/[0.08] bg-[#090D0B]`}
      >
        <div
          ref={containerRef}
          className={`h-full w-full ${drawingMode ? "cursor-crosshair" : ""}`}
          aria-label="Interactive MapLibre GL field map"
        />

        {/* Top-left live status & geodesic readout */}
        <div className="pointer-events-none absolute top-3 left-3 max-w-xs rounded-lg border border-white/[0.10] bg-[#0B0F0D]/90 px-3 py-2 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${mapReady ? "bg-emerald-400" : "bg-zinc-500"}`}
              aria-hidden="true"
            />
            <span className="font-mono text-[11px] font-medium text-zinc-200">
              {editable
                ? `Polygon Editor · ${vertices.length} vertices`
                : `MapLibre GL · ${fields.filter((f) => f.boundary_geojson).length} mapped`}
            </span>
          </div>
          {editable ? (
            <p className="mt-1 text-[11px] text-zinc-400">
              {draftValidationError ? (
                <span className="text-rose-300">{draftValidationError}</span>
              ) : draftPolygon ? (
                <span className="font-mono text-emerald-300">
                  Geodesic Area: {draftAreaHa.toFixed(4)} ha (drag dots to reshape, right-click to delete)
                </span>
              ) : (
                "Click map to add 3+ boundary vertices. Coordinates are never fabricated."
              )}
            </p>
          ) : (
            <p className="mt-1 text-[11px] text-zinc-400">
              {fields.filter((f) => f.boundary_geojson).length > 0
                ? "Click any emerald parcel polygon to inspect or edit."
                : "No field polygons saved yet. Select or create a field to draw its boundary."}
            </p>
          )}
        </div>

        {/* Bottom-right live cursor coordinates */}
        <div className="pointer-events-none absolute right-3 bottom-3 rounded-md border border-white/[0.09] bg-[#0B0F0D]/90 px-2.5 py-1 font-mono text-[11px] text-zinc-300 tabular-nums backdrop-blur-md">
          LNG {cursor.lng.toFixed(5)} · LAT {cursor.lat.toFixed(5)} · Z{cursor.zoom.toFixed(1)}
        </div>
      </div>
    </div>
  );
}

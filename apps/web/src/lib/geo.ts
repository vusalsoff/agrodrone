import type { GeoJsonPolygon } from "@/types/api";

const WGS84_RADIUS_METERS = 6_378_137.0;

function toRadians(deg: number): number {
  return (deg * Math.PI) / 180;
}

/**
 * Compute WGS-84 geodesic area in square meters using the Chamberlain & Duquette algorithm.
 * Mirrors apps/api/app/services/geo.py so live MapLibre polygon previews match saved values.
 */
export function computeRingAreaM2(closedRing: number[][]): number {
  if (closedRing.length < 4) return 0;
  const pts = closedRing.slice(0, -1);
  const n = pts.length;
  let total = 0;

  for (let i = 0; i < n; i++) {
    const p1 = pts[i];
    const p2 = pts[(i + 1) % n];
    const p3 = pts[(i + 2) % n];
    total += (toRadians(p3[0]) - toRadians(p1[0])) * Math.sin(toRadians(p2[1]));
  }

  return Math.abs((total * WGS84_RADIUS_METERS * WGS84_RADIUS_METERS) / 2);
}

export function computePolygonAreaHectares(polygon: GeoJsonPolygon | null | undefined): number {
  if (!polygon || polygon.type !== "Polygon" || !polygon.coordinates.length) return 0;
  const exterior = computeRingAreaM2(polygon.coordinates[0]);
  const holes = polygon.coordinates.slice(1).reduce((sum, ring) => sum + computeRingAreaM2(ring), 0);
  return Math.round(Math.max(0, exterior - holes) / 10_000 * 10000) / 10000;
}

export function verticesToClosedPolygon(vertices: [number, number][]): GeoJsonPolygon | null {
  if (vertices.length < 3) return null;
  const rounded = vertices.map(([lng, lat]) => [
    Math.round(lng * 1e7) / 1e7,
    Math.round(lat * 1e7) / 1e7,
  ]);
  const closed = [...rounded, [rounded[0][0], rounded[0][1]]];
  return {
    type: "Polygon",
    coordinates: [closed],
  };
}

export function polygonToEditableVertices(polygon: GeoJsonPolygon | null | undefined): [number, number][] {
  if (!polygon || polygon.type !== "Polygon" || !polygon.coordinates[0]?.length) {
    return [];
  }
  const ring = polygon.coordinates[0];
  const open = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]
    ? ring.slice(0, -1)
    : ring;
  return open.map((pos) => [pos[0], pos[1]]);
}

function orientation(a: [number, number], b: [number, number], c: [number, number]): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function segmentsIntersect(
  a1: [number, number],
  a2: [number, number],
  b1: [number, number],
  b2: [number, number],
): boolean {
  const o1 = orientation(a1, a2, b1);
  const o2 = orientation(a1, a2, b2);
  const o3 = orientation(b1, b2, a1);
  const o4 = orientation(b1, b2, a2);
  return ((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0));
}

export function validateEditableVertices(vertices: [number, number][]): string | null {
  if (vertices.length < 3) {
    return "Place at least 3 vertices on the map to form a valid field boundary.";
  }
  const closed: [number, number][] = [...vertices, vertices[0]];
  const edgeCount = closed.length - 1;
  for (let i = 0; i < edgeCount; i++) {
    for (let j = i + 1; j < edgeCount; j++) {
      if (j === i + 1 || (i === 0 && j === edgeCount - 1)) continue;
      if (segmentsIntersect(closed[i], closed[i + 1], closed[j], closed[j + 1])) {
        return "Polygon edges cannot cross each other (self-intersecting boundary).";
      }
    }
  }
  const poly = verticesToClosedPolygon(vertices);
  if (!poly || computePolygonAreaHectares(poly) <= 0.0001) {
    return "Polygon area is too small to be saved as an agricultural field.";
  }
  return null;
}

export function getPolygonBounds(
  polygons: GeoJsonPolygon[],
): [[number, number], [number, number]] | null {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;

  for (const poly of polygons) {
    for (const ring of poly.coordinates) {
      for (const [lng, lat] of ring) {
        if (lng < minLng) minLng = lng;
        if (lat < minLat) minLat = lat;
        if (lng > maxLng) maxLng = lng;
        if (lat > maxLat) maxLat = lat;
      }
    }
  }

  if (!Number.isFinite(minLng)) return null;
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

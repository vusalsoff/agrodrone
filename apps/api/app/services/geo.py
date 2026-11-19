"""Geodesic GeoJSON Polygon validation, self-intersection check, area (hectares), and centroid."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import ValidationAppError

# WGS-84 equatorial/authalic reference radius (Chamberlain & Duquette geodesic area formula).
WGS84_RADIUS_METERS = 6_378_137.0


@dataclass(frozen=True)
class PolygonMetrics:
    normalized_geojson: dict[str, Any]
    area_hectares: float
    centroid_lat: float
    centroid_lng: float


def _ring_geodesic_area_m2(ring: list[list[float]]) -> float:
    """Compute geodesic area in square meters for a closed WGS-84 linear ring."""
    count = len(ring)
    if count < 4:
        return 0.0

    # Strip duplicate closing vertex so loop spans unique vertices cleanly.
    pts = ring[:-1]
    n = len(pts)
    total = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        lon1 = math.radians(p1[0])
        lat2 = math.radians(p2[1])
        lon3 = math.radians(p3[0])
        total += (lon3 - lon1) * math.sin(lat2)

    return abs(total * (WGS84_RADIUS_METERS**2) / 2.0)


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    eps = 1e-12
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def _segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if (o1 > 0 and o2 < 0 or o1 < 0 and o2 > 0) and (o3 > 0 and o4 < 0 or o3 < 0 and o4 > 0):
        return True
    if abs(o1) <= 1e-12 and _on_segment(a1, a2, b1):
        return True
    if abs(o2) <= 1e-12 and _on_segment(a1, a2, b2):
        return True
    if abs(o3) <= 1e-12 and _on_segment(b1, b2, a1):
        return True
    return abs(o4) <= 1e-12 and _on_segment(b1, b2, a2)


def _has_self_intersection(ring: list[list[float]]) -> bool:
    """Detect whether non-adjacent edges of a closed linear ring intersect."""
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i in range(len(ring) - 1):
        edges.append(((ring[i][0], ring[i][1]), (ring[i + 1][0], ring[i + 1][1])))

    num_edges = len(edges)
    for i in range(num_edges):
        for j in range(i + 1, num_edges):
            # Adjacent edges share a vertex (including first and last edge).
            if j == i + 1 or (i == 0 and j == num_edges - 1):
                continue
            if _segments_intersect(edges[i][0], edges[i][1], edges[j][0], edges[j][1]):
                return True
    return False


def _validate_ring(raw_ring: Any, ring_index: int) -> list[list[float]]:
    if not isinstance(raw_ring, list) or len(raw_ring) < 4:
        raise ValidationAppError(
            f"Polygon ring {ring_index} must contain at least 4 coordinate positions (3 vertices + closing point)."
        )

    parsed: list[list[float]] = []
    for pos_index, raw_pos in enumerate(raw_ring):
        if not isinstance(raw_pos, (list, tuple)) or len(raw_pos) < 2:
            raise ValidationAppError(
                f"Coordinate at ring {ring_index}, index {pos_index} must be [longitude, latitude]."
            )
        lng_raw, lat_raw = raw_pos[0], raw_pos[1]
        if not isinstance(lng_raw, (int, float)) or not isinstance(lat_raw, (int, float)):
            raise ValidationAppError(
                f"Coordinate at ring {ring_index}, index {pos_index} must contain numeric values."
            )
        lng, lat = float(lng_raw), float(lat_raw)
        if not (math.isfinite(lng) and math.isfinite(lat)):
            raise ValidationAppError("Polygon coordinates must be finite numbers.")
        if not (-180.0 <= lng <= 180.0) or not (-90.0 <= lat <= 90.0):
            raise ValidationAppError(
                f"Coordinate [{lng}, {lat}] is outside valid WGS-84 bounds (lng -180..180, lat -90..90)."
            )
        parsed.append([round(lng, 7), round(lat, 7)])

    if parsed[0] != parsed[-1]:
        raise ValidationAppError(
            f"Polygon ring {ring_index} must be explicitly closed (first coordinate must equal last)."
        )

    unique_vertices = parsed[:-1]
    if len(unique_vertices) < 3:
        raise ValidationAppError(f"Polygon ring {ring_index} must have at least 3 distinct vertices.")

    for i in range(len(parsed) - 1):
        if parsed[i] == parsed[i + 1]:
            raise ValidationAppError(
                f"Polygon ring {ring_index} contains duplicate consecutive coordinates."
            )

    if _has_self_intersection(parsed):
        raise ValidationAppError(f"Polygon ring {ring_index} must not self-intersect.")

    return parsed


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Compute signed planar centroid for a non-degenerate polygon ring (lng, lat)."""
    pts = ring[:-1]
    n = len(pts)
    signed_area_2 = 0.0
    cx = 0.0
    cy = 0.0

    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        signed_area_2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    if abs(signed_area_2) < 1e-12:
        avg_lng = sum(p[0] for p in pts) / n
        avg_lat = sum(p[1] for p in pts) / n
        return round(avg_lng, 6), round(avg_lat, 6)

    factor = 1.0 / (3.0 * signed_area_2)
    return round(cx * factor, 6), round(cy * factor, 6)


def validate_and_measure_polygon(geojson: Any) -> PolygonMetrics:
    """Validate a GeoJSON Polygon geometry and compute geodesic area (ha) and centroid."""
    if not isinstance(geojson, dict):
        raise ValidationAppError("Field boundary must be a GeoJSON Polygon object.")

    # Allow GeoJSON Feature wrapper if strictly wrapping a Polygon, normalizing to Geometry.
    geometry = geojson.get("geometry") if geojson.get("type") == "Feature" else geojson
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValidationAppError("Field boundary must have GeoJSON type 'Polygon'.")

    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) == 0:
        raise ValidationAppError("Polygon 'coordinates' must be a non-empty array of linear rings.")

    validated_rings = [_validate_ring(ring, idx) for idx, ring in enumerate(coords)]
    exterior_m2 = _ring_geodesic_area_m2(validated_rings[0])
    holes_m2 = sum(_ring_geodesic_area_m2(hole) for hole in validated_rings[1:])
    net_m2 = exterior_m2 - holes_m2

    if net_m2 <= 1.0:
        raise ValidationAppError(
            "Polygon area is degenerate or too small (must exceed 1 square meter)."
        )

    centroid_lng, centroid_lat = _ring_centroid(validated_rings[0])
    area_hectares = round(net_m2 / 10_000.0, 4)

    return PolygonMetrics(
        normalized_geojson={"type": "Polygon", "coordinates": validated_rings},
        area_hectares=area_hectares,
        centroid_lat=centroid_lat,
        centroid_lng=centroid_lng,
    )

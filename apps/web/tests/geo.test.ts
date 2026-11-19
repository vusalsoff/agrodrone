import { describe, expect, it } from "vitest";

import {
  computePolygonAreaHectares,
  validateEditableVertices,
  verticesToClosedPolygon,
} from "@/lib/geo";

describe("Client-side WGS-84 geodesic polygon math & validation", () => {
  it("computes accurate geodesic area in hectares matching backend formula", () => {
    const vertices: [number, number][] = [
      [49.85, 40.4],
      [49.8618, 40.4],
      [49.8618, 40.409],
      [49.85, 40.409],
    ];
    expect(validateEditableVertices(vertices)).toBeNull();
    const polygon = verticesToClosedPolygon(vertices);
    expect(polygon).not.toBeNull();
    const areaHa = computePolygonAreaHectares(polygon);
    expect(areaHa).toBeGreaterThan(98);
    expect(areaHa).toBeLessThan(103);
  });

  it("rejects fewer than 3 vertices", () => {
    const err = validateEditableVertices([
      [49.85, 40.4],
      [49.86, 40.4],
    ]);
    expect(err).toMatch(/at least 3 vertices/i);
  });

  it("rejects self-intersecting bowtie polygons", () => {
    const err = validateEditableVertices([
      [49.8, 40.4],
      [49.9, 40.5],
      [49.9, 40.4],
      [49.8, 40.5],
    ]);
    expect(err).toMatch(/self-intersecting/i);
  });
});

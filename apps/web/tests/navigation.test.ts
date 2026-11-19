import { describe, expect, it } from "vitest";

import { ALL_NAV_ITEMS, findNavItemByPath } from "@/lib/navigation";

describe("Platform navigation architecture", () => {
  it("registers all 12 AgroDrone modules (11 core + Media Library) with unique routes", () => {
    expect(ALL_NAV_ITEMS).toHaveLength(12);
    const routes = new Set(ALL_NAV_ITEMS.map((item) => item.href));
    expect(routes.size).toBe(12);
  });

  it("includes every operational and intelligence module route", () => {
    const routes = ALL_NAV_ITEMS.map((item) => item.href);
    expect(routes).toEqual(
      expect.arrayContaining([
        "/",
        "/monitoring",
        "/detection",
        "/fields",
        "/maps",
        "/missions",
        "/media",
        "/history",
        "/alerts",
        "/reports",
        "/devices",
        "/settings",
      ]),
    );
  });

  it("resolves active navigation items accurately by pathname", () => {
    expect(findNavItemByPath("/")?.id).toBe("overview");
    expect(findNavItemByPath("/media")?.id).toBe("media");
    expect(findNavItemByPath("/detection")?.id).toBe("detection");
    expect(findNavItemByPath("/maps")?.id).toBe("maps");
    expect(findNavItemByPath("/devices")?.id).toBe("devices");
  });
});

export type NavIconKey =
  | "layout-dashboard"
  | "radio"
  | "scan-eye"
  | "sprout"
  | "map"
  | "compass"
  | "image"
  | "history"
  | "bell"
  | "file-bar-chart"
  | "cpu"
  | "settings";

export interface NavItem {
  id: string;
  label: string;
  shortLabel: string;
  href: string;
  icon: NavIconKey;
  phase: string;
  status: "active" | "schema_ready" | "planned";
  description: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Operations",
    items: [
      {
        id: "overview",
        label: "Overview Dashboard",
        shortLabel: "Overview",
        href: "/",
        icon: "layout-dashboard",
        phase: "P2",
        status: "active",
        description: "Platform health, live database state, and operational summary.",
      },
      {
        id: "missions",
        label: "Mission Management",
        shortLabel: "Missions",
        href: "/missions",
        icon: "compass",
        phase: "P2",
        status: "active",
        description: "Manual aerial capture logs, lifecycle transitions, and observations.",
      },
      {
        id: "media",
        label: "Media Library",
        shortLabel: "Media",
        href: "/media",
        icon: "image",
        phase: "P2",
        status: "active",
        description: "Secure image & video uploads, preview gallery, and authorized downloads.",
      },
      {
        id: "monitoring",
        label: "Live Monitoring",
        shortLabel: "Monitoring",
        href: "/monitoring",
        icon: "radio",
        phase: "P4",
        status: "active",
        description: "Authenticated ESP32-CAM Edge Gateway stream relay, snapshots, and AI inspection.",
      },
    ],
  },
  {
    label: "Geospatial & Assets",
    items: [
      {
        id: "fields",
        label: "Field Management",
        shortLabel: "Fields",
        href: "/fields",
        icon: "sprout",
        phase: "P2",
        status: "active",
        description: "Agricultural parcel registry, crop metadata, and GeoJSON boundaries.",
      },
      {
        id: "maps",
        label: "Interactive Field Maps",
        shortLabel: "Field Maps",
        href: "/maps",
        icon: "map",
        phase: "P2",
        status: "active",
        description: "MapLibre GL polygon drawing, editing, and geodesic field visualization.",
      },
      {
        id: "devices",
        label: "Device Management",
        shortLabel: "Devices",
        href: "/devices",
        icon: "cpu",
        phase: "P2",
        status: "active",
        description: "Drone airframes, ESP32-CAM modules, and Field Edge Gateway inventory.",
      },
    ],
  },
  {
    label: "Intelligence",
    items: [
      {
        id: "detection",
        label: "AI Detection",
        shortLabel: "AI Detection",
        href: "/detection",
        icon: "scan-eye",
        phase: "P3",
        status: "active",
        description: "Server-side YOLO image & sampled-video analysis workspace.",
      },
      {
        id: "history",
        label: "Detection History",
        shortLabel: "History",
        href: "/history",
        icon: "history",
        phase: "P3",
        status: "active",
        description: "Inference audit trail, model provenance, and human review triage.",
      },
      {
        id: "alerts",
        label: "Alerts & Notifications",
        shortLabel: "Alerts",
        href: "/alerts",
        icon: "bell",
        phase: "P5",
        status: "schema_ready",
        description: "System and validated agricultural anomaly alerts.",
      },
      {
        id: "reports",
        label: "Reports & Analytics",
        shortLabel: "Reports",
        href: "/reports",
        icon: "file-bar-chart",
        phase: "P5",
        status: "planned",
        description: "Exportable mission intelligence and verified detection summaries.",
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        id: "settings",
        label: "User Settings",
        shortLabel: "Settings",
        href: "/settings",
        icon: "settings",
        phase: "P2",
        status: "active",
        description: "Sessions, Admin RBAC user roles, audit logs, and design tokens.",
      },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

export function findNavItemByPath(pathname: string): NavItem | undefined {
  if (pathname === "/") {
    return ALL_NAV_ITEMS.find((item) => item.href === "/");
  }
  return ALL_NAV_ITEMS.find((item) => item.href !== "/" && pathname.startsWith(item.href));
}

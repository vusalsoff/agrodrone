import {
  Bell,
  Compass,
  Cpu,
  FileBarChart2,
  History,
  Image as ImageIcon,
  LayoutDashboard,
  Map,
  Radio,
  ScanEye,
  Settings,
  Sprout,
  type LucideProps,
} from "lucide-react";

import type { NavIconKey } from "@/lib/navigation";

const ICON_MAP: Record<NavIconKey, React.ComponentType<LucideProps>> = {
  "layout-dashboard": LayoutDashboard,
  radio: Radio,
  "scan-eye": ScanEye,
  sprout: Sprout,
  map: Map,
  compass: Compass,
  image: ImageIcon,
  history: History,
  bell: Bell,
  "file-bar-chart": FileBarChart2,
  cpu: Cpu,
  settings: Settings,
};

export function NavIcon({ name, className }: { name: NavIconKey; className?: string }) {
  const Icon = ICON_MAP[name];
  return <Icon className={className} aria-hidden="true" />;
}

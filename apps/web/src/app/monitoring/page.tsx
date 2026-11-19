import type { Metadata } from "next";

import { MonitoringView } from "@/components/modules/monitoring-view";

export const metadata: Metadata = {
  title: "Live Monitoring",
};

export default function MonitoringPage() {
  return <MonitoringView />;
}

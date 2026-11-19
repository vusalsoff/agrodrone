import type { Metadata } from "next";

import { DevicesView } from "@/components/modules/devices-view";

export const metadata: Metadata = {
  title: "Device Management",
};

export default function DevicesPage() {
  return <DevicesView />;
}

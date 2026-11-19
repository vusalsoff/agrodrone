import type { Metadata } from "next";

import { MissionsView } from "@/components/modules/missions-view";

export const metadata: Metadata = {
  title: "Mission Management",
};

export default function MissionsPage() {
  return <MissionsView />;
}

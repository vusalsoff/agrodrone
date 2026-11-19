import type { Metadata } from "next";

import { DetectionView } from "@/components/modules/detection-view";

export const metadata: Metadata = {
  title: "AI Detection",
};

export default function DetectionPage() {
  return <DetectionView />;
}

import type { Metadata } from "next";

import { DetectionDetailView } from "@/components/modules/detection-detail-view";

export const metadata: Metadata = {
  title: "Detection Detail",
};

export default async function DetectionDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <DetectionDetailView jobId={jobId} />;
}

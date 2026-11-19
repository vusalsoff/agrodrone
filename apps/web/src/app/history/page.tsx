import type { Metadata } from "next";

import { HistoryView } from "@/components/modules/history-view";

export const metadata: Metadata = {
  title: "Detection History",
};

export default function HistoryPage() {
  return <HistoryView />;
}

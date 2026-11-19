import type { Metadata } from "next";

import { ReportsView } from "@/components/modules/reports-view";

export const metadata: Metadata = {
  title: "Reports & Analytics",
};

export default function ReportsPage() {
  return <ReportsView />;
}

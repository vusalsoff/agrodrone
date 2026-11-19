import type { Metadata } from "next";

import { MapsView } from "@/components/modules/maps-view";

export const metadata: Metadata = {
  title: "Interactive Field Maps",
};

export default function MapsPage() {
  return <MapsView />;
}

import type { Metadata } from "next";

import { MediaView } from "@/components/modules/media-view";

export const metadata: Metadata = {
  title: "Media Library",
};

export default function MediaPage() {
  return <MediaView />;
}

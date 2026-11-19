import type { Metadata } from "next";

import { FieldsView } from "@/components/modules/fields-view";

export const metadata: Metadata = {
  title: "Field Management",
};

export default function FieldsPage() {
  return <FieldsView />;
}

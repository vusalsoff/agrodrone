import type { Metadata } from "next";

import { SettingsView } from "@/components/modules/settings-view";

export const metadata: Metadata = {
  title: "User Settings",
};

export default function SettingsPage() {
  return <SettingsView />;
}

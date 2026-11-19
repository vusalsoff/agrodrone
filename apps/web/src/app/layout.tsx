import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppShell } from "@/components/layout/app-shell";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "AgroDrone — Agricultural Intelligence Platform",
    template: "%s | AgroDrone",
  },
  description:
    "Enterprise agricultural field monitoring, server-side computer vision, and mission intelligence platform.",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AgroDrone",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#080B0A",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} dark`}>
      <body className="min-h-screen bg-[#080B0A] font-sans text-zinc-100 antialiased selection:bg-emerald-500/25 selection:text-emerald-200">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

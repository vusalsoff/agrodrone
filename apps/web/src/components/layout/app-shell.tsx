"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { MotionConfig } from "framer-motion";
import { Loader2 } from "lucide-react";

import { AuthProvider, useAuth } from "@/components/layout/auth-context";
import { LanguageProvider } from "@/components/layout/language-context";
import { Sidebar } from "@/components/layout/sidebar";
import { SystemProvider } from "@/components/layout/system-context";
import { Topbar } from "@/components/layout/topbar";
import { ToastProvider } from "@/components/ui/toast";

const PUBLIC_AUTH_ROUTES = new Set(["/login", "/register"]);

function ShellFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { loading } = useAuth();
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const isAuthPage = PUBLIC_AUTH_ROUTES.has(pathname);

  React.useEffect(() => {
    if (isAuthPage) {
      router.replace("/");
    }
  }, [isAuthPage, router]);

  if (isAuthPage) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#080B0A] text-zinc-300">
        <Loader2 className="h-5 w-5 animate-spin text-emerald-400" />
        <p className="mt-3 font-mono text-xs text-zinc-500">Opening AgroDrone Dashboard...</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#080B0A] text-zinc-300">
        <Loader2 className="h-5 w-5 animate-spin text-emerald-400" />
        <p className="mt-3 font-mono text-xs text-zinc-500">Loading AgroDrone workspace...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#080B0A] text-zinc-100">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((prev) => !prev)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMobileMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[1420px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <LanguageProvider>
        <ToastProvider>
          <AuthProvider>
            <SystemProvider>
              <ShellFrame>{children}</ShellFrame>
            </SystemProvider>
          </AuthProvider>
        </ToastProvider>
      </LanguageProvider>
    </MotionConfig>
  );
}

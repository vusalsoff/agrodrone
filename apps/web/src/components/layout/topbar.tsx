"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, CheckCheck, ExternalLink, Menu, RefreshCw, Shield } from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { NAV_LABEL_AZ, useLanguage } from "@/components/layout/language-context";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/status-dot";
import { apiClient } from "@/lib/api-client";
import { appEnv } from "@/lib/env";
import { findNavItemByPath } from "@/lib/navigation";
import { cn, formatLatency, formatTimestamp } from "@/lib/utils";
import type { NotificationRead } from "@/types/api";

interface TopbarProps {
  onOpenMobileMenu: () => void;
}

export function Topbar({ onOpenMobileMenu }: TopbarProps) {
  const pathname = usePathname();
  const activeItem = findNavItemByPath(pathname);
  const { health, loading, error, refresh } = useSystemState();
  const { user } = useAuth();
  const { lang, setLang, tr } = useLanguage();
  const [unreadCount, setUnreadCount] = React.useState(0);
  const [notifOpen, setNotifOpen] = React.useState(false);
  const [recentNotifs, setRecentNotifs] = React.useState<NotificationRead[]>([]);

  const loadUnread = React.useCallback(async () => {
    if (!user) {
      setUnreadCount(0);
      return;
    }
    try {
      const res = await apiClient.getUnreadNotificationCount();
      setUnreadCount(res.unread_count);
    } catch {
      // ignore background poll errors
    }
  }, [user]);

  React.useEffect(() => {
    void loadUnread();
    if (!user) return;
    const timer = window.setInterval(() => void loadUnread(), 30000);
    return () => window.clearInterval(timer);
  }, [loadUnread, user]);

  const toggleNotifMenu = async () => {
    const next = !notifOpen;
    setNotifOpen(next);
    if (next && user) {
      try {
        const res = await apiClient.listNotifications({ limit: 8 });
        setRecentNotifs(res.items);
      } catch {
        // ignore
      }
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await apiClient.markAllNotificationsRead();
      setUnreadCount(0);
      setRecentNotifs((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch {
      // ignore
    }
  };

  const apiTone = loading
    ? "neutral"
    : error || !health
      ? "rose"
      : health.status === "ok"
        ? "emerald"
        : "amber";

  const apiLabel = loading
    ? tr("Checking API...", "API yoxlanılır...")
    : error || !health
      ? tr("API Unreachable", "API əlçatan deyil")
      : `${tr("API Online", "API Aktivdir")} · ${formatLatency(health.database_latency_ms)}`;

  const activeTitle = activeItem
    ? lang === "az"
      ? (NAV_LABEL_AZ[activeItem.href] ?? activeItem.label)
      : activeItem.label
    : tr("Workspace", "İş sahəsi");

  return (
    <header className="surface-glass sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-x-0 border-t-0 px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileMenu}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.08] text-zinc-300 hover:bg-white/[0.06] lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-4 w-4" />
        </button>

        <div className="flex min-w-0 items-center gap-2 text-xs">
          <span className="hidden text-zinc-500 sm:inline">AgroDrone</span>
          <span className="hidden text-zinc-700 sm:inline">/</span>
          <span className="truncate font-medium text-zinc-100">
            {activeTitle}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div
          className="inline-flex items-center rounded-lg border border-white/[0.08] bg-white/[0.03] p-0.5 text-[11px] font-medium"
          role="group"
          aria-label={tr("Language switcher", "Dil seçimi")}
        >
          <button
            type="button"
            onClick={() => setLang("en")}
            className={cn(
              "rounded-md px-2 py-0.5 transition-colors",
              lang === "en" ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:text-zinc-200",
            )}
          >
            EN
          </button>
          <button
            type="button"
            onClick={() => setLang("az")}
            className={cn(
              "rounded-md px-2 py-0.5 transition-colors",
              lang === "az" ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:text-zinc-200",
            )}
          >
            AZ
          </button>
        </div>

        <div
          className={cn(
            "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[11px]",
            apiTone === "emerald" && "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
            apiTone === "amber" && "border-amber-500/25 bg-amber-500/10 text-amber-300",
            apiTone === "rose" && "border-rose-500/30 bg-rose-500/10 text-rose-300",
            apiTone === "neutral" && "border-white/[0.08] bg-white/[0.03] text-zinc-400",
          )}
          role="status"
          aria-live="polite"
        >
          <StatusDot tone={apiTone} pulse={apiTone === "emerald"} />
          <span className="hidden sm:inline">{apiLabel}</span>
          <span className="sm:hidden">{apiTone === "emerald" ? "Online" : "Offline"}</span>
        </div>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Refresh backend status"
          title="Refresh live backend status"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
        </Button>

        {user ? (
          <div className="flex items-center gap-2 pl-1">
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void toggleNotifMenu()}
                aria-label="Notification center"
                title="Notifications"
                className="relative"
              >
                <Bell className="h-4 w-4 text-zinc-300" />
                {unreadCount > 0 ? (
                  <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-emerald-500 px-1 font-mono text-[10px] font-semibold text-zinc-950">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                ) : null}
              </Button>
              {notifOpen ? (
                <div className="surface-glass absolute right-0 mt-2 w-80 rounded-xl border border-white/[0.1] bg-[#0b1015]/95 p-3 shadow-2xl backdrop-blur-xl">
                  <div className="mb-2 flex items-center justify-between border-b border-white/[0.08] pb-2">
                    <span className="text-xs font-semibold text-zinc-100">{tr("Notifications", "Bildirişlər")}</span>
                    <div className="flex items-center gap-2">
                      {unreadCount > 0 ? (
                        <button
                          type="button"
                          onClick={() => void handleMarkAllRead()}
                          className="inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:text-emerald-300"
                        >
                          <CheckCheck className="h-3 w-3" />
                          {tr("Read all", "Hamısını oxu")}
                        </button>
                      ) : null}
                      <Link
                        href="/alerts"
                        onClick={() => setNotifOpen(false)}
                        className="text-[11px] text-zinc-400 hover:text-zinc-200"
                      >
                        {tr("Open Alerts", "Xəbərdarlıqlara keç")}
                      </Link>
                    </div>
                  </div>
                  {recentNotifs.length === 0 ? (
                    <p className="py-4 text-center text-xs text-zinc-500">
                      {tr("No notifications recorded yet.", "Hələlik bildiriş yoxdur.")}
                    </p>
                  ) : (
                    <ul className="max-h-64 space-y-2 overflow-y-auto">
                      {recentNotifs.map((n) => (
                        <li
                          key={n.id}
                          className={cn(
                            "rounded-lg border p-2 text-xs",
                            n.is_read
                              ? "border-white/[0.05] bg-white/[0.01] text-zinc-400"
                              : "border-emerald-500/25 bg-emerald-500/[0.06] text-zinc-100",
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate font-medium">{n.title}</span>
                            <Badge
                              tone={
                                n.severity === "critical"
                                  ? "rose"
                                  : n.severity === "warning"
                                    ? "amber"
                                    : "neutral"
                              }
                            >
                              {n.severity}
                            </Badge>
                          </div>
                          <p className="mt-1 line-clamp-2 text-[11px] text-zinc-400">{n.message}</p>
                          <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-500">
                            <span>{formatTimestamp(n.created_at)}</span>
                            {n.link_path ? (
                              <Link
                                href={n.link_path}
                                onClick={() => setNotifOpen(false)}
                                className="text-emerald-400 hover:underline"
                              >
                                Inspect
                              </Link>
                            ) : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}
            </div>
            <Link
              href="/settings"
              className="hidden items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-xs transition-colors hover:border-emerald-500/30 md:inline-flex"
            >
              <Shield className="h-3.5 w-3.5 text-emerald-400" />
              <span className="max-w-[120px] truncate font-medium text-zinc-100">
                {user.full_name}
              </span>
              <Badge tone="emerald" className="px-1.5 py-0 font-mono text-[10px] uppercase">
                {user.role}
              </Badge>
            </Link>
          </div>
        ) : null}

        <Button variant="ghost" size="icon" asChild className="hidden xl:inline-flex" title="OpenAPI Docs">
          <a href={`${appEnv.apiBaseUrl}/docs`} target="_blank" rel="noreferrer" aria-label="OpenAPI Docs">
            <ExternalLink className="h-3.5 w-3.5 text-zinc-400" />
          </a>
        </Button>
      </div>
    </header>
  );
}

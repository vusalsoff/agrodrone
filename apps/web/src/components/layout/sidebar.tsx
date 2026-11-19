"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen, WifiOff, X } from "lucide-react";

import { NAV_GROUP_AZ, NAV_LABEL_AZ, useLanguage } from "@/components/layout/language-context";
import { NavIcon } from "@/components/layout/nav-icon";
import { StatusDot } from "@/components/ui/status-dot";
import { NAV_GROUPS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

function BrandMark() {
  return (
    <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10">
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M12 3L20 7.5V16.5L12 21L4 16.5V7.5L12 3Z"
          stroke="#34D399"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="12" r="2.75" fill="#10B981" />
        <path
          d="M12 3V9.25M20 7.5L14.4 10.65M4 7.5L9.6 10.65"
          stroke="#34D399"
          strokeOpacity="0.6"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

export function Sidebar({
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}: SidebarProps) {
  const pathname = usePathname();
  const { lang, tr } = useLanguage();

  const renderNav = (compact: boolean) => (
    <div className="flex h-full flex-col">
      {/* Brand header */}
      <div
        className={cn(
          "flex h-14 items-center border-b border-white/[0.06] px-3.5",
          compact ? "justify-center" : "justify-between",
        )}
      >
        <Link
          href="/"
          onClick={onCloseMobile}
          className="flex items-center gap-2.5 overflow-hidden"
        >
          <BrandMark />
          {!compact && (
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-sm font-semibold tracking-tight text-zinc-100">
                  AgroDrone
                </span>
                <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[9px] font-medium uppercase tracking-wider text-emerald-300">
                  PRO
                </span>
              </div>
              <p className="truncate text-[10px] text-zinc-500">
                {tr("Agricultural Intelligence", "Ağıllı Kənd Təsərrüfatı")}
              </p>
            </div>
          )}
        </Link>

        {!compact && (
          <button
            type="button"
            onClick={onToggleCollapse}
            className="hidden h-7 w-7 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-white/[0.06] hover:text-zinc-200 lg:inline-flex"
            aria-label="Collapse navigation sidebar"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        )}

        <button
          type="button"
          onClick={onCloseMobile}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-200 lg:hidden"
          aria-label="Close navigation menu"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Navigation groups */}
      <nav
        aria-label="Primary platform navigation"
        className="flex-1 space-y-5 overflow-y-auto px-2.5 py-4"
      >
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            {!compact && (
              <div className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                {lang === "az" ? (NAV_GROUP_AZ[group.label] ?? group.label) : group.label}
              </div>
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const isActive =
                  item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                const itemLabel = lang === "az" ? (NAV_LABEL_AZ[item.href] ?? item.shortLabel) : item.shortLabel;

                return (
                  <li key={item.id}>
                    <Link
                      href={item.href}
                      onClick={onCloseMobile}
                      title={compact ? `${itemLabel} (${item.phase})` : undefined}
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "group relative flex items-center rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                        compact ? "justify-center" : "justify-between gap-2.5",
                        isActive
                          ? "text-zinc-50"
                          : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200",
                      )}
                    >
                      {isActive && (
                        <motion.span
                          layoutId="agrodrone-nav-active"
                          transition={{ type: "spring", stiffness: 380, damping: 34 }}
                          className="absolute inset-0 rounded-lg border border-emerald-500/25 bg-emerald-500/[0.11]"
                        />
                      )}

                      <span className="relative z-10 flex min-w-0 items-center gap-2.5">
                        <NavIcon
                          name={item.icon}
                          className={cn(
                            "h-4 w-4 shrink-0 transition-colors",
                            isActive
                              ? "text-emerald-400"
                              : "text-zinc-500 group-hover:text-zinc-300",
                          )}
                        />
                        {!compact && <span className="truncate">{itemLabel}</span>}
                      </span>

                      {!compact && (
                        <span
                          className={cn(
                            "relative z-10 font-mono text-[10px]",
                            item.status === "active"
                              ? "text-emerald-400/90"
                              : "text-zinc-500",
                          )}
                        >
                          {item.phase}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Bottom hardware boundary card + expand button */}
      <div className="border-t border-white/[0.06] p-3">
        {compact ? (
          <button
            type="button"
            onClick={onToggleCollapse}
            className="mx-auto flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-200"
            aria-label="Expand navigation sidebar"
            title="Expand sidebar"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        ) : (
          <div className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <WifiOff className="h-3.5 w-3.5 text-amber-400" aria-hidden="true" />
                <span className="text-[11px] font-medium text-zinc-200">ESP32-CAM AP</span>
              </div>
              <StatusDot tone="amber" />
            </div>
            <p className="mt-1.5 font-mono text-[10px] text-zinc-400">
              SSID: agroDrone · 192.168.4.1
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-zinc-500">
              {tr(
                "Isolated local AP. Cloud relay requires Edge Gateway CLI.",
                "Yerli Wi-Fi AP. Bulud ötürməsi üçün Edge Gateway CLI tələb olunur.",
              )}
            </p>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop persistent sidebar */}
      <aside
        className={cn(
          "hidden shrink-0 border-r border-white/[0.07] bg-[#0B0F0D] transition-[width] duration-200 lg:block",
          collapsed ? "w-[70px]" : "w-[252px]",
        )}
      >
        <div className="sticky top-0 h-screen">{renderNav(collapsed)}</div>
      </aside>

      {/* Mobile slide-over drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden" role="dialog" aria-modal="true">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-xs"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          <aside className="relative z-10 h-full w-[264px] border-r border-white/[0.08] bg-[#0B0F0D]">
            {renderNav(false)}
          </aside>
        </div>
      )}
    </>
  );
}

"use client";

import * as React from "react";
import { motion } from "framer-motion";

import { useLanguage } from "@/components/layout/language-context";
import { Badge } from "@/components/ui/badge";

const TITLE_AZ: Record<string, string> = {
  "Field Management": "Sahələrin İdarə Edilməsi",
  "Interactive Field Maps": "İnteraktiv Sahə Xəritələri",
  "Device Management": "Cihazların İdarə Edilməsi",
  "Mission Management": "Missiyaların İdarə Edilməsi",
  "Media Library": "Media Kitabxanası",
  "AgroVision AI Detection": "AgroVision AI Aşkarlama",
  "Detection History": "Aşkarlama Tarixçəsi",
  "Alerts & Notifications": "Xəbərdarlıqlar və Bildirişlər",
  "Reports & Analytics": "Hesabatlar və Analitika",
  "User Settings & Security": "İstifadəçi Parametrləri və Təhlükəsizlik",
  "Detection Job Detail": "Analiz İşinin Təfərrüatı",
};

const DESC_AZ: Record<string, string> = {
  "Manage agricultural parcels, crop classifications, and geospatial polygons.":
    "Kənd təsərrüfatı sahələrini, bitki növlərini və xəritə sərhədlərini idarə edin.",
  "Draw, edit, validate, and measure agricultural parcel polygons with MapLibre GL.":
    "MapLibre GL ilə sahə sərhədlərini çəkin, redaktə edin və ölçün.",
  "Register physical drone airframes, ESP32-CAM modules, and field sensors.":
    "Dronları, ESP32-CAM kameralarını və sahə sensorlarını qeydiyyata alın.",
  "Plan and log manual E88 + ESP32-CAM field surveys, lifecycle states, and linked media.":
    "Sahə müşahidə missiyalarını planlaşdırın, statusları izləyin və media əlavə edin.",
  "Upload, validate, preview, and download field imagery and mission video.":
    "Sahə şəkillərini və videolarını yükləyin, önizləyin və endirin.",
  "Run server-side Ultralytics YOLO object detection on uploaded field imagery and video.":
    "Yüklənmiş sahə şəkilləri və videoları üzərində YOLOv8n obyekt aşkarlaması aparın.",
  "Auditable archive of AI detection runs, model provenance, and human review states.":
    "AI analizlərinin tarixçəsi, model məlumatları və insan təsdiqi statusları.",
  "Event-driven alert rules, deduplication/cooldowns, ESP32-CAM warnings, and notification center.":
    "Hadisə əsaslı xəbərdarlıq qaydaları, kamera xəbərdarlıqları və bildiriş mərkəzi.",
  "Real database-backed analytics, deduplicated video summaries, and CSV / JSON / PDF exports.":
    "Real verilənlər bazası analitikası, video xülasələri və CSV / JSON / PDF ixracı.",
  "Active session management, Admin RBAC user roles, security audit logs, and hardware limits.":
    "Sessiya idarəetməsi, istifadəçi rolları, təhlükəsizlik jurnalları və avadanlıq məhdudiyyətləri.",
};

interface PageHeaderProps {
  title: string;
  description: string;
  phaseBadge: string;
  phaseTone?: "emerald" | "amber" | "neutral";
  actions?: React.ReactNode;
}

export function PageHeader({
  title,
  description,
  phaseBadge,
  phaseTone = "neutral",
  actions,
}: PageHeaderProps) {
  const { lang } = useLanguage();
  const displayTitle = lang === "az" ? (TITLE_AZ[title] ?? title) : title;
  const displayDescription = lang === "az" ? (DESC_AZ[description] ?? description) : description;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="mb-6 flex flex-col justify-between gap-4 border-b border-white/[0.06] pb-5 sm:flex-row sm:items-end"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-50 sm:text-2xl">
            {displayTitle}
          </h1>
          <Badge tone={phaseTone} className="font-mono">
            {phaseBadge}
          </Badge>
        </div>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-zinc-400">{displayDescription}</p>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </motion.div>
  );
}

"use client";

import * as React from "react";

export type Language = "en" | "az";

const STORAGE_KEY = "agrodrone.lang";

interface LanguageContextValue {
  lang: Language;
  setLang: (lang: Language) => void;
  toggleLang: () => void;
  tr: (en: string, az: string) => string;
}

const defaultContext: LanguageContextValue = {
  lang: "en",
  setLang: () => {},
  toggleLang: () => {},
  tr: (en: string) => en,
};

const LanguageContext = React.createContext<LanguageContextValue>(defaultContext);

export const NAV_GROUP_AZ: Record<string, string> = {
  OPERATIONS: "ƏMƏLİYYATLAR",
  "GEOSPATIAL & ASSETS": "XƏRİTƏ VƏ RESURSLAR",
  INTELLIGENCE: "SÜNİ İNTELLEKT",
  SYSTEM: "SİSTEM",
};

export const NAV_LABEL_AZ: Record<string, string> = {
  "/": "Ümumi Baxış",
  "/missions": "Missiyalar",
  "/media": "Media",
  "/monitoring": "Canlı Monitorinq",
  "/fields": "Sahələr",
  "/maps": "Sahə Xəritələri",
  "/devices": "Cihazlar",
  "/detection": "AI Aşkarlama",
  "/history": "Tarixçə",
  "/alerts": "Xəbərdarlıqlar",
  "/reports": "Hesabatlar",
  "/settings": "Parametrlər",
};

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = React.useState<Language>("en");

  React.useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "az" || saved === "en") {
        setLangState(saved);
        document.documentElement.lang = saved;
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  const setLang = React.useCallback((next: Language) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
      document.documentElement.lang = next;
    } catch {
      // ignore storage errors
    }
  }, []);

  const toggleLang = React.useCallback(() => {
    setLang(lang === "en" ? "az" : "en");
  }, [lang, setLang]);

  const tr = React.useCallback(
    (en: string, az: string) => (lang === "az" ? az : en),
    [lang],
  );

  const value = React.useMemo(
    () => ({ lang, setLang, toggleLang, tr }),
    [lang, setLang, toggleLang, tr],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  return React.useContext(LanguageContext);
}

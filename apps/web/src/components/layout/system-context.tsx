"use client";

import * as React from "react";

import { apiClient, ApiClientError } from "@/lib/api-client";
import type {
  CapabilitiesResponse,
  HealthResponse,
  SystemStatusResponse,
} from "@/types/api";

interface SystemContextValue {
  health: HealthResponse | null;
  status: SystemStatusResponse | null;
  capabilities: CapabilitiesResponse | null;
  loading: boolean;
  error: string | null;
  lastCheckedAt: string | null;
  refresh: () => Promise<void>;
}

const SystemContext = React.createContext<SystemContextValue | null>(null);

export function SystemProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [status, setStatus] = React.useState<SystemStatusResponse | null>(null);
  const [capabilities, setCapabilities] = React.useState<CapabilitiesResponse | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthData, statusData, capabilitiesData] = await Promise.all([
        apiClient.getHealth(),
        apiClient.getSystemStatus(),
        apiClient.getCapabilities(),
      ]);
      setHealth(healthData);
      setStatus(statusData);
      setCapabilities(capabilitiesData);
      setLastCheckedAt(new Date().toISOString());
    } catch (err) {
      setHealth(null);
      setStatus(null);
      setCapabilities(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to contact AgroDrone backend API.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = React.useMemo<SystemContextValue>(
    () => ({
      health,
      status,
      capabilities,
      loading,
      error,
      lastCheckedAt,
      refresh,
    }),
    [health, status, capabilities, loading, error, lastCheckedAt, refresh],
  );

  return <SystemContext.Provider value={value}>{children}</SystemContext.Provider>;
}

export function useSystemState(): SystemContextValue {
  const ctx = React.useContext(SystemContext);
  if (!ctx) {
    throw new Error("useSystemState must be used inside SystemProvider.");
  }
  return ctx;
}

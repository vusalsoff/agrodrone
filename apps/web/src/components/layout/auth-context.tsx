"use client";

import * as React from "react";

import { apiClient, setUnauthorizedListener } from "@/lib/api-client";
import type { LoginRequest, RegisterRequest, UserRead } from "@/types/api";

interface AuthContextValue {
  user: UserRead | null;
  loading: boolean;
  isAdmin: boolean;
  canManageFields: boolean;
  canOperate: boolean;
  isViewer: boolean;
  login: (payload: LoginRequest) => Promise<UserRead>;
  register: (payload: RegisterRequest) => Promise<UserRead>;
  logout: (logoutAll?: boolean) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<UserRead | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);

  const refreshUser = React.useCallback(async () => {
    setLoading(true);
    try {
      const me = await apiClient.getMe();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    setUnauthorizedListener(() => {
      setUser(null);
    });
    void refreshUser();
    return () => setUnauthorizedListener(null);
  }, [refreshUser]);

  const login = React.useCallback(async (payload: LoginRequest) => {
    const session = await apiClient.login(payload);
    setUser(session.user);
    return session.user;
  }, []);

  const register = React.useCallback(async (payload: RegisterRequest) => {
    const session = await apiClient.register(payload);
    setUser(session.user);
    return session.user;
  }, []);

  const logout = React.useCallback(async (logoutAll = false) => {
    try {
      await apiClient.logout(logoutAll);
    } finally {
      setUser(null);
    }
  }, []);

  const role = user?.role ?? null;
  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAdmin: role === "admin",
      canManageFields: role === "admin" || role === "agronomist",
      canOperate: role === "admin" || role === "agronomist" || role === "operator",
      isViewer: role === "viewer",
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, loading, role, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return ctx;
}

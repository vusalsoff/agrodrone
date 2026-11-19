"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  FileClock,
  KeyRound,
  LogOut,
  Palette,
  ServerCog,
  ShieldCheck,
  Users,
} from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { PageHeader } from "@/components/layout/page-header";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form-controls";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusDot } from "@/components/ui/status-dot";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { appEnv } from "@/lib/env";
import type {
  AuditLogRead,
  AuthPolicyResponse,
  UserRead,
  UserRole,
} from "@/types/api";

const COLOR_TOKENS = [
  { name: "Obsidian Canvas", hex: "#080B0A", usage: "Primary application background" },
  { name: "Charcoal Surface", hex: "#0E1311", usage: "Sidebar and base cards" },
  { name: "Elevated Slate", hex: "#131A17", usage: "Nested surfaces and panels" },
  { name: "Emerald Primary", hex: "#10B981", usage: "Primary action and active accents" },
  { name: "Emerald Highlight", hex: "#34D399", usage: "Dark-mode telemetry legibility" },
  { name: "Amber Isolation", hex: "#F59E0B", usage: "Local AP / pending phase warning" },
];

export function SettingsView() {
  const router = useRouter();
  const { user, isAdmin, logout } = useAuth();
  const { health } = useSystemState();
  const { notify } = useToast();

  const [authPolicy, setAuthPolicy] = React.useState<AuthPolicyResponse | null>(null);
  const [users, setUsers] = React.useState<UserRead[]>([]);
  const [auditLogs, setAuditLogs] = React.useState<AuditLogRead[]>([]);
  const [adminLoading, setAdminLoading] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    apiClient
      .getAuthPolicy()
      .then((res) => {
        if (active) setAuthPolicy(res);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const loadAdminData = React.useCallback(async () => {
    if (!isAdmin) return;
    setAdminLoading(true);
    try {
      const [uRes, aRes] = await Promise.all([
        apiClient.listUsers(100, 0),
        apiClient.listAuditLogs({ limit: 50 }),
      ]);
      setUsers(uRes.items);
      setAuditLogs(aRes.items);
    } catch {
      // Handled gracefully
    } finally {
      setAdminLoading(false);
    }
  }, [isAdmin]);

  React.useEffect(() => {
    void loadAdminData();
  }, [loadAdminData]);

  const handleRoleChange = async (targetUser: UserRead, nextRole: UserRole) => {
    try {
      const updated = await apiClient.updateUserRole(targetUser.id, nextRole);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      notify({
        tone: "success",
        title: "Role updated",
        description: `${updated.full_name} is now ${updated.role}.`,
      });
      await loadAdminData();
    } catch (err) {
      notify({
        tone: "error",
        title: "Role update blocked",
        description: err instanceof ApiClientError ? err.message : "Could not update role.",
      });
    }
  };

  const handleLogout = async (logoutAll: boolean) => {
    await logout(logoutAll);
    notify({
      tone: "info",
      title: logoutAll ? "All sessions revoked" : "Signed out",
    });
    router.replace("/login");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="User Settings & Security"
        description="Active session management, Admin RBAC user roles, security audit logs, and enterprise design tokens."
        phaseBadge="Phase 2 · Auth & RBAC Active"
        phaseTone="emerald"
      />

      <Tabs defaultValue="account">
        <TabsList className="flex-wrap">
          <TabsTrigger value="account">Account & Security</TabsTrigger>
          {isAdmin && <TabsTrigger value="users">Users & RBAC</TabsTrigger>}
          {isAdmin && <TabsTrigger value="audit">Audit Logs</TabsTrigger>}
          <TabsTrigger value="runtime">Runtime & API</TabsTrigger>
          <TabsTrigger value="design">Design System</TabsTrigger>
        </TabsList>

        <TabsContent value="account">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <Panel className="lg:col-span-6">
              <PanelHeader>
                <div>
                  <PanelTitle>Authenticated Operator Profile</PanelTitle>
                  <PanelDescription>Session secured via HttpOnly cookies, CSRF double-submit, and refresh rotation.</PanelDescription>
                </div>
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
              </PanelHeader>
              <PanelBody className="space-y-4 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-white/[0.025] p-3">
                    <span className="text-[10px] uppercase text-zinc-500">Full Name</span>
                    <p className="mt-0.5 font-medium text-zinc-100">{user?.full_name ?? "—"}</p>
                  </div>
                  <div className="rounded-lg bg-white/[0.025] p-3">
                    <span className="text-[10px] uppercase text-zinc-500">Role</span>
                    <div className="mt-1">
                      <Badge tone="emerald" className="font-mono uppercase">
                        {user?.role ?? "—"}
                      </Badge>
                    </div>
                  </div>
                  <div className="col-span-2 rounded-lg bg-white/[0.025] p-3">
                    <span className="text-[10px] uppercase text-zinc-500">Email Address</span>
                    <p className="mt-0.5 font-mono text-zinc-200">{user?.email ?? "—"}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 border-t border-white/[0.06] pt-3">
                  <Button variant="outline" size="sm" onClick={() => void handleLogout(false)}>
                    <LogOut className="h-3.5 w-3.5" />
                    <span>Sign Out Current Session</span>
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => void handleLogout(true)}>
                    <span>Revoke All Sessions</span>
                  </Button>
                </div>
              </PanelBody>
            </Panel>

            <Panel className="lg:col-span-6">
              <PanelHeader>
                <div>
                  <PanelTitle>Active Security Posture</PanelTitle>
                  <PanelDescription>
                    Live readout from <code className="font-mono text-zinc-300">GET /api/v1/auth/policy</code>
                  </PanelDescription>
                </div>
                <KeyRound className="h-4 w-4 text-emerald-400" />
              </PanelHeader>
              <PanelBody className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5">
                  <span className="text-zinc-400">Password Hashing</span>
                  <span className="font-mono text-zinc-100">
                    {authPolicy?.password_hashing ?? "Argon2id (argon2-cffi)"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5">
                  <span className="text-zinc-400">Token Lifecycle</span>
                  <span className="font-mono text-zinc-100">
                    {authPolicy?.token_scheme ?? "JWT + HttpOnly rotating refresh"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5">
                  <span className="text-zinc-400">CSRF Protection</span>
                  <span className="font-mono text-emerald-300">
                    {authPolicy?.csrf_protection ?? "Double-submit cookie"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5">
                  <span className="text-zinc-400">Auth Rate Limit</span>
                  <span className="font-mono text-zinc-200">
                    {authPolicy?.rate_limiting ?? "Sliding window per IP"}
                  </span>
                </div>
              </PanelBody>
            </Panel>
          </div>
        </TabsContent>

        {isAdmin && (
          <TabsContent value="users">
            <Panel>
              <PanelHeader>
                <div>
                  <PanelTitle>Workspace Users & Role-Based Access Control</PanelTitle>
                  <PanelDescription>
                    Enforced server-side across Fields, Devices, Missions, Media, and Admin endpoints.
                  </PanelDescription>
                </div>
                <Users className="h-4 w-4 text-emerald-400" />
              </PanelHeader>
              <PanelBody className="p-0">
                {adminLoading ? (
                  <div className="space-y-2 p-5">
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-xs">
                      <thead>
                        <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wider text-zinc-500">
                          <th className="px-5 py-3 font-semibold">User</th>
                          <th className="px-5 py-3 font-semibold">Status</th>
                          <th className="px-5 py-3 font-semibold">Role</th>
                          <th className="px-5 py-3 font-semibold">Joined</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.05]">
                        {users.map((u) => (
                          <tr key={u.id} className="hover:bg-white/[0.02]">
                            <td className="px-5 py-3">
                              <div className="font-medium text-zinc-100">{u.full_name}</div>
                              <div className="font-mono text-[11px] text-zinc-400">{u.email}</div>
                            </td>
                            <td className="px-5 py-3">
                              <Badge tone={u.is_active ? "emerald" : "rose"}>
                                {u.is_active ? "Active" : "Inactive"}
                              </Badge>
                            </td>
                            <td className="px-5 py-3">
                              <Select
                                aria-label={`Role for ${u.email}`}
                                value={u.role}
                                disabled={u.id === user?.id}
                                onChange={(e) => void handleRoleChange(u, e.target.value as UserRole)}
                                className="h-8 w-36 text-xs"
                              >
                                <option value="admin">admin</option>
                                <option value="agronomist">agronomist</option>
                                <option value="operator">operator</option>
                                <option value="viewer">viewer</option>
                              </Select>
                            </td>
                            <td className="px-5 py-3 font-mono text-[11px] text-zinc-400">
                              {new Date(u.created_at).toLocaleDateString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </PanelBody>
            </Panel>
          </TabsContent>
        )}

        {isAdmin && (
          <TabsContent value="audit">
            <Panel>
              <PanelHeader>
                <div>
                  <PanelTitle>Security & Mutation Audit Log</PanelTitle>
                  <PanelDescription>
                    Immutable log of authentication events, role changes, CRUD mutations, and media uploads (credentials redacted).
                  </PanelDescription>
                </div>
                <FileClock className="h-4 w-4 text-emerald-400" />
              </PanelHeader>
              <PanelBody className="p-0">
                {adminLoading ? (
                  <div className="space-y-2 p-5">
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-xs">
                      <thead>
                        <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-wider text-zinc-500">
                          <th className="px-5 py-3 font-semibold">Timestamp</th>
                          <th className="px-5 py-3 font-semibold">Action</th>
                          <th className="px-5 py-3 font-semibold">Actor</th>
                          <th className="px-5 py-3 font-semibold">Resource</th>
                          <th className="px-5 py-3 font-semibold">IP</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.05]">
                        {auditLogs.map((log) => (
                          <tr key={log.id} className="hover:bg-white/[0.02]">
                            <td className="px-5 py-2.5 font-mono text-[11px] text-zinc-400">
                              {new Date(log.created_at).toLocaleString()}
                            </td>
                            <td className="px-5 py-2.5">
                              <Badge
                                tone={
                                  log.action.includes("failed") || log.action.includes("reuse")
                                    ? "rose"
                                    : "emerald"
                                }
                                className="font-mono"
                              >
                                {log.action}
                              </Badge>
                            </td>
                            <td className="px-5 py-2.5 font-mono text-[11px] text-zinc-300">
                              {log.actor_email ?? "system"}
                            </td>
                            <td className="px-5 py-2.5 font-mono text-[11px] text-zinc-400">
                              {log.resource_type}
                              {log.resource_id ? `:${log.resource_id.slice(0, 8)}` : ""}
                            </td>
                            <td className="px-5 py-2.5 font-mono text-[11px] text-zinc-500">
                              {log.ip_address ?? "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </PanelBody>
            </Panel>
          </TabsContent>
        )}

        <TabsContent value="runtime">
          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Environment & Endpoint Configuration</PanelTitle>
                <PanelDescription>
                  Non-secret runtime parameters bound via <code className="font-mono text-zinc-300">.env</code>.
                </PanelDescription>
              </div>
              <ServerCog className="h-4 w-4 text-zinc-400" />
            </PanelHeader>
            <PanelBody className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3.5">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                  Frontend API Base URL
                </div>
                <div className="mt-1 font-mono text-emerald-300">{appEnv.apiBaseUrl}</div>
              </div>
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3.5">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                  Active Environment
                </div>
                <div className="mt-1 font-mono text-zinc-200 uppercase">
                  {health?.environment ?? appEnv.environment}
                </div>
              </div>
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3.5">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                  Backend Version
                </div>
                <div className="mt-1 font-mono text-zinc-200">{health?.version ?? "—"}</div>
              </div>
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3.5">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                  Database Dialect
                </div>
                <div className="mt-1 font-mono text-zinc-200 uppercase">
                  {health?.database_dialect ?? "—"}
                </div>
              </div>
            </PanelBody>
          </Panel>
        </TabsContent>

        <TabsContent value="design">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <Panel className="lg:col-span-7">
              <PanelHeader>
                <div>
                  <PanelTitle>Color Tokens & Surface Hierarchy</PanelTitle>
                  <PanelDescription>
                    Obsidian charcoal surfaces with restrained emerald operational accents.
                  </PanelDescription>
                </div>
                <Palette className="h-4 w-4 text-emerald-400" />
              </PanelHeader>
              <PanelBody className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {COLOR_TOKENS.map((token) => (
                  <div
                    key={token.name}
                    className="flex items-center gap-3 rounded-lg border border-white/[0.07] bg-white/[0.02] p-3"
                  >
                    <span
                      className="h-9 w-9 shrink-0 rounded-lg border border-white/15"
                      style={{ backgroundColor: token.hex }}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-zinc-100">{token.name}</p>
                      <p className="font-mono text-[10px] text-zinc-400">{token.hex}</p>
                      <p className="truncate text-[10px] text-zinc-500">{token.usage}</p>
                    </div>
                  </div>
                ))}
              </PanelBody>
            </Panel>

            <Panel className="lg:col-span-5">
              <PanelHeader>
                <div>
                  <PanelTitle>Component Primitives</PanelTitle>
                  <PanelDescription>Accessible enterprise interactive tokens.</PanelDescription>
                </div>
              </PanelHeader>
              <PanelBody className="space-y-4">
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                    Buttons
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="primary" size="sm">Primary</Button>
                    <Button variant="secondary" size="sm">Secondary</Button>
                    <Button variant="subtle" size="sm">Subtle</Button>
                    <Button variant="outline" size="sm">Outline</Button>
                    <Button variant="ghost" size="sm">Ghost</Button>
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                    Status Badges
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Badge tone="emerald">
                      <StatusDot tone="emerald" />
                      Operational
                    </Badge>
                    <Badge tone="amber">
                      <StatusDot tone="amber" />
                      Isolated AP
                    </Badge>
                    <Badge tone="rose">
                      <StatusDot tone="rose" />
                      Degraded
                    </Badge>
                    <Badge tone="neutral">Schema Ready</Badge>
                  </div>
                </div>
              </PanelBody>
            </Panel>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

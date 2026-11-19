"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, Lock, ShieldCheck, UserPlus } from "lucide-react";

import { useAuth } from "@/components/layout/auth-context";
import { useSystemState } from "@/components/layout/system-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldLabel, FormError, Input, Select } from "@/components/ui/form-controls";
import { Panel, PanelBody } from "@/components/ui/panel";
import { StatusDot } from "@/components/ui/status-dot";
import { useToast } from "@/components/ui/toast";
import { apiClient, ApiClientError } from "@/lib/api-client";
import type { AuthPolicyResponse, SelfRegisterRole } from "@/types/api";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next") || "/";
  const { user, login, register } = useAuth();
  const { health } = useSystemState();
  const { notify } = useToast();

  const [policy, setPolicy] = React.useState<AuthPolicyResponse | null>(null);
  const [email, setEmail] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState<SelfRegisterRole>("agronomist");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (user) {
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
    }
  }, [user, router, nextPath]);

  React.useEffect(() => {
    let active = true;
    apiClient
      .getAuthPolicy()
      .then((res) => {
        if (active) setPolicy(res);
      })
      .catch(() => {
        // Handled cleanly via API status pill
      });
    return () => {
      active = false;
    };
  }, []);

  const passwordChecks = [
    { label: "At least 8 characters", ok: password.length >= 8 },
    { label: "Uppercase & lowercase letters", ok: /[A-Z]/.test(password) && /[a-z]/.test(password) },
    { label: "Includes a digit", ok: /\d/.test(password) },
  ];

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }

    if (mode === "register") {
      if (fullName.trim().length < 2) {
        setError("Please enter your full name (at least 2 characters).");
        return;
      }
      if (!passwordChecks.every((c) => c.ok)) {
        setError("Password must meet all security strength criteria.");
        return;
      }
    }

    setSubmitting(true);
    try {
      const signedIn =
        mode === "login"
          ? await login({ email: email.trim(), password })
          : await register({
              email: email.trim(),
              full_name: fullName.trim(),
              password,
              role,
            });
      notify({
        tone: "success",
        title: mode === "login" ? "Authenticated" : "Account created",
        description: `Signed in as ${signedIn.full_name} (${signedIn.role}).`,
      });
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : "Authentication failed. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="topo-grid flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        {/* Brand header */}
        <div className="flex flex-col items-center text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
          </div>
          <h1 className="mt-4 text-xl font-semibold tracking-tight text-zinc-50">
            {mode === "login" ? "Sign in to AgroDrone" : "Create AgroDrone Account"}
          </h1>
          <p className="mt-1 text-xs text-zinc-400">
            Enterprise Agricultural Intelligence Platform · Argon2id + HttpOnly Rotating Sessions
          </p>
          <div className="mt-3 flex items-center gap-2">
            <Badge tone={health?.status === "ok" ? "emerald" : "rose"} className="font-mono">
              <StatusDot tone={health?.status === "ok" ? "emerald" : "rose"} />
              <span>{health?.status === "ok" ? "API Online" : "API Offline"}</span>
            </Badge>
            {policy?.bootstrap_required && (
              <Badge tone="amber" className="font-mono">
                First Account = Admin Bootstrap
              </Badge>
            )}
          </div>
        </div>

        <Panel>
          <PanelBody className="space-y-4">
            {mode === "login" && policy?.bootstrap_required && (
              <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/[0.07] p-3 text-xs text-emerald-200">
                No user accounts exist yet.{" "}
                <Link href="/register" className="font-semibold underline hover:text-emerald-100">
                  Register the initial Administrator account
                </Link>{" "}
                to begin managing fields, devices, missions, and media.
              </div>
            )}

            <FormError message={error} />

            <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4" noValidate>
              {mode === "register" && (
                <div>
                  <FieldLabel htmlFor="auth-fullname" required>
                    Full Name
                  </FieldLabel>
                  <Input
                    id="auth-fullname"
                    type="text"
                    autoComplete="name"
                    placeholder="e.g., Leyla Mammadova"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                  />
                </div>
              )}

              <div>
                <FieldLabel htmlFor="auth-email" required>
                  Work Email
                </FieldLabel>
                <Input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  placeholder="operator@farm.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <div>
                <FieldLabel htmlFor="auth-password" required>
                  Password
                </FieldLabel>
                <Input
                  id="auth-password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  placeholder={mode === "login" ? "Enter your password" : "Minimum 8 chars, mixed case + digit"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                {mode === "register" && (
                  <ul className="mt-2 space-y-1">
                    {passwordChecks.map((check) => (
                      <li
                        key={check.label}
                        className={`flex items-center gap-1.5 text-[11px] ${
                          check.ok ? "text-emerald-300" : "text-zinc-500"
                        }`}
                      >
                        <Check className="h-3 w-3" />
                        <span>{check.label}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {mode === "register" && !policy?.bootstrap_required && (
                <div>
                  <FieldLabel htmlFor="auth-role">Workspace Role</FieldLabel>
                  <Select
                    id="auth-role"
                    value={role}
                    onChange={(e) => setRole(e.target.value as SelfRegisterRole)}
                  >
                    <option value="agronomist">Agronomist (Fields, Maps, Devices, Missions, Media)</option>
                    <option value="operator">Operator (Devices, Missions, Media)</option>
                    <option value="viewer">Viewer (Read-only)</option>
                  </Select>
                  <p className="mt-1 text-[11px] text-zinc-500">
                    Admin privileges can only be granted by an existing Administrator.
                  </p>
                </div>
              )}

              <Button type="submit" variant="primary" size="lg" className="w-full" disabled={submitting}>
                {mode === "login" ? (
                  <>
                    <Lock className="h-4 w-4" />
                    <span>{submitting ? "Signing in..." : "Sign In"}</span>
                  </>
                ) : (
                  <>
                    <UserPlus className="h-4 w-4" />
                    <span>
                      {submitting
                        ? "Creating account..."
                        : policy?.bootstrap_required
                          ? "Create Initial Admin Account"
                          : "Create Account"}
                    </span>
                  </>
                )}
              </Button>
            </form>
          </PanelBody>
        </Panel>

        <p className="text-center text-xs text-zinc-400">
          {mode === "login" ? (
            <>
              Need an operator account?{" "}
              <Link href="/register" className="font-medium text-emerald-400 hover:text-emerald-300">
                Create one
              </Link>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <Link href="/login" className="font-medium text-emerald-400 hover:text-emerald-300">
                Sign in
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

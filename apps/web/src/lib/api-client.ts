import { appEnv } from "@/lib/env";
import type {
  AlertRead,
  ApiErrorEnvelope,
  AuditLogRead,
  AuthPolicyResponse,
  AuthSessionResponse,
  CapabilitiesResponse,
  DatasetRead,
  DetectionItemRead,
  DetectionItemReviewRequest,
  DetectionJobCreateRequest,
  DetectionJobDetailRead,
  DetectionJobRead,
  DeviceCreate,
  DeviceRead,
  DeviceUpdate,
  FieldCreate,
  FieldRead,
  FieldUpdate,
  GatewayDiagnosticsResponse,
  GatewayEnrollRequest,
  GatewayEnrollResponse,
  GatewayRead,
  HealthResponse,
  LoginRequest,
  MediaAssetRead,
  MediaDownloadUrlResponse,
  MissionCreate,
  MissionRead,
  MissionStatus,
  MissionUpdate,
  ModelRegistryItem,
  PaginatedResponse,
  RegisterRequest,
  StreamSessionRead,
  SystemStatusResponse,
  UserRead,
  UserRole,
} from "@/types/api";

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(
    message: string,
    status: number,
    code = "REQUEST_FAILED",
    requestId: string | null = null,
    details: unknown = null,
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

let cachedCsrfToken: string | null = null;
let refreshInFlight: Promise<AuthSessionResponse> | null = null;
let unauthorizedListener: (() => void) | null = null;

export function setCsrfToken(token: string | null): void {
  cachedCsrfToken = token;
}

export function setUnauthorizedListener(listener: (() => void) | null): void {
  unauthorizedListener = listener;
}

export function readCsrfToken(): string | null {
  if (typeof document !== "undefined") {
    const match = document.cookie
      .split("; ")
      .find((row) => row.startsWith("agrodrone_csrf_token="));
    if (match) {
      return decodeURIComponent(match.split("=").slice(1).join("="));
    }
  }
  return cachedCsrfToken;
}

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      qs.set(key, String(value));
    }
  }
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : "";
}

async function parseError(response: Response): Promise<ApiClientError> {
  let envelope: ApiErrorEnvelope | null = null;
  try {
    envelope = (await response.json()) as ApiErrorEnvelope;
  } catch {
    // Non-JSON error response
  }
  return new ApiClientError(
    envelope?.error?.message ?? `API responded with status ${response.status}`,
    response.status,
    envelope?.error?.code ?? `HTTP_${response.status}`,
    envelope?.request_id ?? response.headers.get("X-Request-ID"),
    envelope?.error?.details ?? null,
  );
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  timeoutMs?: number;
  retryOn401?: boolean;
}

async function performRefresh(): Promise<AuthSessionResponse> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const headers: Record<string, string> = { Accept: "application/json" };
      const csrf = readCsrfToken();
      if (csrf) {
        headers["X-CSRF-Token"] = csrf;
      }
      const res = await fetch(`${appEnv.apiBaseUrl}/api/v1/auth/refresh`, {
        method: "POST",
        headers,
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) {
        setCsrfToken(null);
        throw await parseError(res);
      }
      const data = (await res.json()) as AuthSessionResponse;
      setCsrfToken(data.csrf_token);
      return data;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    timeoutMs = 8000,
    retryOn401 = !path.startsWith("/api/v1/auth/login") &&
      !path.startsWith("/api/v1/auth/register") &&
      !path.startsWith("/api/v1/auth/refresh"),
  } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (method !== "GET") {
    const csrf = readCsrfToken();
    if (csrf) {
      headers["X-CSRF-Token"] = csrf;
    }
  }

  try {
    const response = await fetch(`${appEnv.apiBaseUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });

    if (response.status === 401 && retryOn401) {
      try {
        await performRefresh();
        return await requestJson<T>(path, { ...options, retryOn401: false });
      } catch {
        unauthorizedListener?.();
        throw await parseError(response);
      }
    }

    if (!response.ok) {
      throw await parseError(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiClientError("API request timed out.", 0, "TIMEOUT");
    }
    throw new ApiClientError(
      "Unable to reach AgroDrone FastAPI backend. Ensure apps/api is running.",
      0,
      "NETWORK_UNREACHABLE",
    );
  } finally {
    clearTimeout(timer);
  }
}

export function uploadMediaWithProgress(
  params: {
    file: File;
    fieldId?: string | null;
    missionId?: string | null;
    notes?: string | null;
  },
  onProgress?: (percent: number) => void,
): Promise<MediaAssetRead> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("file", params.file);
    if (params.fieldId) formData.append("field_id", params.fieldId);
    if (params.missionId) formData.append("mission_id", params.missionId);
    if (params.notes?.trim()) formData.append("notes", params.notes.trim());

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${appEnv.apiBaseUrl}/api/v1/media/upload`, true);
    xhr.withCredentials = true;

    const csrf = readCsrfToken();
    if (csrf) {
      xhr.setRequestHeader("X-CSRF-Token", csrf);
    }

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onProgress) {
        onProgress(Math.min(100, Math.round((evt.loaded / evt.total) * 100)));
      }
    };

    xhr.onerror = () => {
      reject(new ApiClientError("Network error while uploading media file.", 0, "NETWORK_ERROR"));
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as MediaAssetRead);
        } catch {
          reject(new ApiClientError("Invalid server response after upload.", xhr.status));
        }
        return;
      }

      try {
        const env = JSON.parse(xhr.responseText) as ApiErrorEnvelope;
        reject(
          new ApiClientError(
            env.error?.message || `Upload failed (${xhr.status})`,
            xhr.status,
            env.error?.code || `HTTP_${xhr.status}`,
            env.request_id,
            env.error?.details,
          ),
        );
      } catch {
        reject(new ApiClientError(`Upload failed with status ${xhr.status}.`, xhr.status));
      }
    };

    xhr.send(formData);
  });
}

export function getMediaContentUrl(mediaId: string, download = false): string {
  const suffix = download ? "?download=true" : "";
  return `${appEnv.apiBaseUrl}/api/v1/media/${mediaId}/content${suffix}`;
}

export function getDetectionAnnotatedUrl(jobId: string, download = false): string {
  const suffix = download ? "?download=true" : "";
  return `${appEnv.apiBaseUrl}/api/v1/detections/jobs/${jobId}/annotated${suffix}`;
}

export function getDetectionFrameAnnotatedUrl(jobId: string, frameIndex: number): string {
  return `${appEnv.apiBaseUrl}/api/v1/detections/jobs/${jobId}/frames/${frameIndex}/annotated`;
}

export function getDetectionExportUrl(jobId: string): string {
  return `${appEnv.apiBaseUrl}/api/v1/detections/jobs/${jobId}/export`;
}

export function getGatewayLatestFrameUrl(gatewayId: string): string {
  return `${appEnv.apiBaseUrl}/api/v1/gateway/${gatewayId}/stream/latest`;
}

export const apiClient = {
  // Health & System
  getHealth: () => requestJson<HealthResponse>("/api/v1/health", { retryOn401: false }),
  getSystemStatus: () =>
    requestJson<SystemStatusResponse>("/api/v1/system/status", { retryOn401: false }),
  getCapabilities: () =>
    requestJson<CapabilitiesResponse>("/api/v1/system/capabilities", { retryOn401: false }),

  // Authentication & RBAC
  getAuthPolicy: () =>
    requestJson<AuthPolicyResponse>("/api/v1/auth/policy", { retryOn401: false }),
  register: async (payload: RegisterRequest) => {
    const res = await requestJson<AuthSessionResponse>("/api/v1/auth/register", {
      method: "POST",
      body: payload,
      retryOn401: false,
    });
    setCsrfToken(res.csrf_token);
    return res;
  },
  login: async (payload: LoginRequest) => {
    const res = await requestJson<AuthSessionResponse>("/api/v1/auth/login", {
      method: "POST",
      body: payload,
      retryOn401: false,
    });
    setCsrfToken(res.csrf_token);
    return res;
  },
  refreshSession: performRefresh,
  logout: async (logoutAll = false) => {
    try {
      await requestJson<void>("/api/v1/auth/logout", {
        method: "POST",
        body: { logout_all: logoutAll },
        retryOn401: false,
      });
    } finally {
      setCsrfToken(null);
    }
  },
  getMe: () => requestJson<UserRead>("/api/v1/auth/me"),
  listUsers: (limit = 50, offset = 0) =>
    requestJson<PaginatedResponse<UserRead>>(
      `/api/v1/auth/users${buildQuery({ limit, offset })}`,
    ),
  updateUserRole: (userId: string, role: UserRole, is_active?: boolean) =>
    requestJson<UserRead>(`/api/v1/auth/users/${userId}/role`, {
      method: "PATCH",
      body: is_active === undefined ? { role } : { role, is_active },
    }),
  listAuditLogs: (params?: { action?: string; limit?: number; offset?: number }) =>
    requestJson<PaginatedResponse<AuditLogRead>>(
      `/api/v1/auth/audit-logs${buildQuery({
        action: params?.action,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),

  // Fields
  listFields: (params?: {
    q?: string;
    crop_type?: string;
    has_boundary?: boolean;
    limit?: number;
    offset?: number;
  }) =>
    requestJson<PaginatedResponse<FieldRead>>(
      `/api/v1/fields${buildQuery({
        q: params?.q,
        crop_type: params?.crop_type,
        has_boundary: params?.has_boundary,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),
  createField: (payload: FieldCreate) =>
    requestJson<FieldRead>("/api/v1/fields", { method: "POST", body: payload }),
  updateField: (fieldId: string, payload: FieldUpdate) =>
    requestJson<FieldRead>(`/api/v1/fields/${fieldId}`, { method: "PATCH", body: payload }),
  deleteField: (fieldId: string) =>
    requestJson<void>(`/api/v1/fields/${fieldId}`, { method: "DELETE" }),

  // Devices
  listDevices: (params?: {
    q?: string;
    device_type?: string;
    status?: string;
    field_id?: string;
    limit?: number;
    offset?: number;
  }) =>
    requestJson<PaginatedResponse<DeviceRead>>(
      `/api/v1/devices${buildQuery({
        q: params?.q,
        device_type: params?.device_type,
        status: params?.status,
        field_id: params?.field_id,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),
  createDevice: (payload: DeviceCreate) =>
    requestJson<DeviceRead>("/api/v1/devices", { method: "POST", body: payload }),
  updateDevice: (deviceId: string, payload: DeviceUpdate) =>
    requestJson<DeviceRead>(`/api/v1/devices/${deviceId}`, { method: "PATCH", body: payload }),
  deleteDevice: (deviceId: string) =>
    requestJson<void>(`/api/v1/devices/${deviceId}`, { method: "DELETE" }),

  // Missions
  listMissions: (params?: {
    q?: string;
    status?: string;
    field_id?: string;
    device_id?: string;
    limit?: number;
    offset?: number;
  }) =>
    requestJson<PaginatedResponse<MissionRead>>(
      `/api/v1/missions${buildQuery({
        q: params?.q,
        status: params?.status,
        field_id: params?.field_id,
        device_id: params?.device_id,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),
  createMission: (payload: MissionCreate) =>
    requestJson<MissionRead>("/api/v1/missions", { method: "POST", body: payload }),
  updateMission: (missionId: string, payload: MissionUpdate) =>
    requestJson<MissionRead>(`/api/v1/missions/${missionId}`, { method: "PATCH", body: payload }),
  transitionMission: (missionId: string, targetStatus: MissionStatus, note?: string) =>
    requestJson<MissionRead>(`/api/v1/missions/${missionId}/transition`, {
      method: "POST",
      body: { target_status: targetStatus, note: note || undefined },
    }),
  addMissionObservation: (missionId: string, note: string) =>
    requestJson<MissionRead>(`/api/v1/missions/${missionId}/observations`, {
      method: "POST",
      body: { note },
    }),
  deleteMission: (missionId: string) =>
    requestJson<void>(`/api/v1/missions/${missionId}`, { method: "DELETE" }),

  // Media
  listMedia: (params?: {
    q?: string;
    media_type?: string;
    field_id?: string;
    mission_id?: string;
    limit?: number;
    offset?: number;
  }) =>
    requestJson<PaginatedResponse<MediaAssetRead>>(
      `/api/v1/media${buildQuery({
        q: params?.q,
        media_type: params?.media_type,
        field_id: params?.field_id,
        mission_id: params?.mission_id,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),
  getMediaDownloadUrl: (mediaId: string, download = false) =>
    requestJson<MediaDownloadUrlResponse>(
      `/api/v1/media/${mediaId}/download-url${buildQuery({ download })}`,
    ),
  deleteMedia: (mediaId: string) =>
    requestJson<void>(`/api/v1/media/${mediaId}`, { method: "DELETE" }),

  // Phase 3 AgroVision AI Engine
  listModels: () => requestJson<ModelRegistryItem[]>("/api/v1/detections/models"),
  listDatasets: (detectionMode?: string) =>
    requestJson<PaginatedResponse<DatasetRead>>(
      `/api/v1/detections/datasets${buildQuery({ detection_mode: detectionMode })}`,
    ),
  createDetectionJob: (payload: DetectionJobCreateRequest) =>
    requestJson<DetectionJobDetailRead>("/api/v1/detections/jobs", {
      method: "POST",
      body: payload,
      timeoutMs: 30000,
    }),
  listDetectionJobs: (params?: {
    q?: string;
    status?: string;
    model_id?: string;
    detection_mode?: string;
    media_type?: string;
    field_id?: string;
    mission_id?: string;
    review_status?: string;
    date_from?: string;
    date_to?: string;
    sort_by?: "newest" | "oldest" | "duration_desc";
    limit?: number;
    offset?: number;
  }) =>
    requestJson<PaginatedResponse<DetectionJobRead>>(
      `/api/v1/detections/jobs${buildQuery({
        q: params?.q,
        status: params?.status,
        model_id: params?.model_id,
        detection_mode: params?.detection_mode,
        media_type: params?.media_type,
        field_id: params?.field_id,
        mission_id: params?.mission_id,
        review_status: params?.review_status,
        date_from: params?.date_from,
        date_to: params?.date_to,
        sort_by: params?.sort_by,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),
  getDetectionJob: (jobId: string) =>
    requestJson<DetectionJobDetailRead>(`/api/v1/detections/jobs/${jobId}`),
  cancelDetectionJob: (jobId: string) =>
    requestJson<DetectionJobRead>(`/api/v1/detections/jobs/${jobId}/cancel`, {
      method: "POST",
    }),
  retryDetectionJob: (jobId: string) =>
    requestJson<DetectionJobDetailRead>(`/api/v1/detections/jobs/${jobId}/retry`, {
      method: "POST",
      timeoutMs: 30000,
    }),
  deleteDetectionJob: (jobId: string) =>
    requestJson<void>(`/api/v1/detections/jobs/${jobId}`, { method: "DELETE" }),
  reviewDetectionItem: (itemId: string, payload: DetectionItemReviewRequest) =>
    requestJson<DetectionItemRead>(`/api/v1/detections/items/${itemId}/review`, {
      method: "PATCH",
      body: payload,
    }),
  listDetections: (limit = 25, offset = 0) =>
    requestJson<PaginatedResponse<DetectionJobRead>>(
      `/api/v1/detections${buildQuery({ limit, offset })}`,
    ),
  listAlerts: (limit = 25, offset = 0) =>
    requestJson<PaginatedResponse<AlertRead>>(
      `/api/v1/alerts${buildQuery({ limit, offset })}`,
    ),

  // Phase 4 Field Edge Gateway & Live Monitoring
  listGateways: (limit = 50, offset = 0) =>
    requestJson<PaginatedResponse<GatewayRead>>(
      `/api/v1/gateway${buildQuery({ limit, offset })}`,
    ),
  enrollGateway: (payload: GatewayEnrollRequest) =>
    requestJson<GatewayEnrollResponse>("/api/v1/gateway/enroll", {
      method: "POST",
      body: payload,
    }),
  rotateGatewayCredential: (gatewayId: string) =>
    requestJson<GatewayEnrollResponse>(`/api/v1/gateway/${gatewayId}/rotate`, {
      method: "POST",
    }),
  revokeGateway: (gatewayId: string) =>
    requestJson<GatewayRead>(`/api/v1/gateway/${gatewayId}/revoke`, {
      method: "POST",
    }),
  getGatewayDiagnostics: (gatewayId: string) =>
    requestJson<GatewayDiagnosticsResponse>(`/api/v1/gateway/${gatewayId}/diagnostics`),
  startGatewayStream: (
    gatewayId: string,
    payload: { target_fps?: number; max_frame_bytes?: number; duration_seconds?: number } = {},
  ) =>
    requestJson<StreamSessionRead>(`/api/v1/gateway/${gatewayId}/stream/start`, {
      method: "POST",
      body: payload,
    }),
  stopGatewayStream: (gatewayId: string) =>
    requestJson<StreamSessionRead | null>(`/api/v1/gateway/${gatewayId}/stream/stop`, {
      method: "POST",
    }),
  listGatewaySnapshots: (gatewayId: string, limit = 25, offset = 0) =>
    requestJson<PaginatedResponse<MediaAssetRead>>(
      `/api/v1/gateway/${gatewayId}/snapshots${buildQuery({ limit, offset })}`,
    ),
  analyzeGatewaySnapshot: (
    mediaId: string,
    payload: { model_id?: string; confidence_threshold?: number } = {},
  ) =>
    requestJson<DetectionJobDetailRead>(`/api/v1/gateway/snapshots/${mediaId}/analyze`, {
      method: "POST",
      body: payload,
    }),
  captureLocalCameraAndAnalyze: (
    payload: { model_id?: string; confidence_threshold?: number } = {},
  ) =>
    requestJson<import("@/types/api").DetectionJobRead>("/api/v1/gateway/local-capture-analyze", {
      method: "POST",
      body: payload,
    }),

  // Phase 5 Smart Analytics, Alerts, Notifications & Reporting
  getAnalyticsOverview: (params?: {
    date_from?: string;
    date_to?: string;
    field_id?: string;
    mission_id?: string;
  }) =>
    requestJson<import("@/types/api").AnalyticsOverviewResponse>(
      `/api/v1/analytics/overview${buildQuery({
        date_from: params?.date_from,
        date_to: params?.date_to,
        field_id: params?.field_id,
        mission_id: params?.mission_id,
      })}`,
    ),
  getMapAnalytics: (params?: { date_from?: string; date_to?: string }) =>
    requestJson<import("@/types/api").MapAnalyticsResponse>(
      `/api/v1/analytics/map-summary${buildQuery({
        date_from: params?.date_from,
        date_to: params?.date_to,
      })}`,
    ),
  listAlertsPhase5: (params?: {
    status?: string;
    severity?: string;
    category?: string;
    limit?: number;
    offset?: number;
  }) =>
    requestJson<PaginatedResponse<import("@/types/api").AlertPhase5Read>>(
      `/api/v1/alerts${buildQuery({
        status: params?.status,
        severity: params?.severity,
        category: params?.category,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      })}`,
    ),
  evaluateGatewayAlerts: () =>
    requestJson<{ checked_gateways: number; offline_detected: number; alerts_created: number }>(
      "/api/v1/alerts/evaluate-gateways",
      { method: "POST" },
    ),
  acknowledgeAlert: (alertId: string) =>
    requestJson<import("@/types/api").AlertPhase5Read>(
      `/api/v1/alerts/${alertId}/acknowledge`,
      { method: "POST" },
    ),
  resolveAlert: (alertId: string, resolutionNotes?: string) =>
    requestJson<import("@/types/api").AlertPhase5Read>(
      `/api/v1/alerts/${alertId}/resolve`,
      { method: "POST", body: { resolution_notes: resolutionNotes ?? null } },
    ),
  listAlertRules: (limit = 50, offset = 0) =>
    requestJson<PaginatedResponse<import("@/types/api").AlertRuleRead>>(
      `/api/v1/alert-rules${buildQuery({ limit, offset })}`,
    ),
  createAlertRule: (payload: import("@/types/api").AlertRuleCreate) =>
    requestJson<import("@/types/api").AlertRuleRead>("/api/v1/alert-rules", {
      method: "POST",
      body: payload,
    }),
  updateAlertRule: (
    ruleId: string,
    payload: Partial<import("@/types/api").AlertRuleCreate>,
  ) =>
    requestJson<import("@/types/api").AlertRuleRead>(`/api/v1/alert-rules/${ruleId}`, {
      method: "PATCH",
      body: payload,
    }),
  deleteAlertRule: (ruleId: string) =>
    requestJson<void>(`/api/v1/alert-rules/${ruleId}`, { method: "DELETE" }),
  listNotifications: (params?: { unread_only?: boolean; limit?: number; offset?: number }) =>
    requestJson<PaginatedResponse<import("@/types/api").NotificationRead>>(
      `/api/v1/notifications${buildQuery({
        unread_only: params?.unread_only,
        limit: params?.limit ?? 25,
        offset: params?.offset ?? 0,
      })}`,
    ),
  getUnreadNotificationCount: () =>
    requestJson<{ unread_count: number }>("/api/v1/notifications/unread-count"),
  markNotificationRead: (notificationId: string) =>
    requestJson<import("@/types/api").NotificationRead>(
      `/api/v1/notifications/${notificationId}/read`,
      { method: "POST" },
    ),
  markAllNotificationsRead: () =>
    requestJson<{ unread_count: number }>("/api/v1/notifications/read-all", {
      method: "POST",
    }),
  getNotificationPreferences: () =>
    requestJson<import("@/types/api").NotificationPreferenceRead>(
      "/api/v1/notifications/preferences",
    ),
  updateNotificationPreferences: (payload: {
    in_app_enabled?: boolean;
    email_enabled?: boolean;
    email_address?: string | null;
    min_severity?: string;
    muted_trigger_types?: string[];
  }) =>
    requestJson<import("@/types/api").NotificationPreferenceRead>(
      "/api/v1/notifications/preferences",
      { method: "PATCH", body: payload },
    ),
  previewReport: (params: {
    report_type: import("@/types/api").ReportType;
    date_from?: string;
    date_to?: string;
    field_id?: string;
    mission_id?: string;
  }) =>
    requestJson<import("@/types/api").ReportPreviewResponse>(
      `/api/v1/reports/preview${buildQuery(params)}`,
    ),
  reportExportUrl: (params: {
    report_type: import("@/types/api").ReportType;
    format: import("@/types/api").ReportFormat;
    date_from?: string;
    date_to?: string;
    field_id?: string;
    mission_id?: string;
  }) => `${appEnv.apiBaseUrl}/api/v1/reports/export${buildQuery(params)}`,
};

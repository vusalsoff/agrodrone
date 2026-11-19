export interface ErrorDetail {
  code: string;
  message: string;
  details: unknown;
}

export interface ApiErrorEnvelope {
  error: ErrorDetail;
  request_id: string | null;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type UserRole = "admin" | "agronomist" | "operator" | "viewer";
export type SelfRegisterRole = "agronomist" | "operator" | "viewer";

export interface UserRead {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthSessionResponse {
  user: UserRead;
  access_token: string;
  token_type: "bearer";
  expires_in_seconds: number;
  csrf_token: string;
}

export interface RegisterRequest {
  email: string;
  full_name: string;
  password: string;
  role?: SelfRegisterRole;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthPolicyResponse {
  status: string;
  password_hashing: string;
  token_scheme: string;
  access_token_expire_minutes: number;
  refresh_token_expire_days: number;
  csrf_protection: string;
  rate_limiting: string;
  supported_roles: UserRole[];
  bootstrap_required: boolean;
  target_phase: string;
}

export interface AuditLogRead {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  request_id: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
  environment: string;
  database_connected: boolean;
  database_dialect: string;
  database_latency_ms: number | null;
  timestamp: string;
}

export interface EntityCounts {
  fields: number;
  devices: number;
  missions: number;
  media_assets: number;
  detection_jobs: number;
  open_alerts: number;
}

export type SubsystemState =
  | "operational"
  | "standby"
  | "unconfigured"
  | "isolated_local"
  | "degraded";

export interface SubsystemStatus {
  id: string;
  name: string;
  status: SubsystemState;
  summary: string;
  target_phase: string;
}

export interface SystemStatusResponse {
  service: string;
  version: string;
  environment: string;
  phase: string;
  database_connected: boolean;
  database_dialect: string;
  database_latency_ms: number | null;
  storage_backend: string;
  ai_inference_enabled: boolean;
  edge_gateway_enabled: boolean;
  counts: EntityCounts;
  subsystems: SubsystemStatus[];
  timestamp: string;
}

export interface HardwareDeviceSpec {
  id: string;
  name: string;
  category: "airframe" | "camera_module" | "programmer" | "power_source";
  connectivity_mode: "manual_rf" | "isolated_ap" | "usb_serial_bench" | "unmanaged_power";
  local_ssid: string | null;
  local_dashboard_url: string | null;
  local_stream_url: string | null;
  cloud_directly_reachable: boolean;
  supported_capabilities: string[];
  unsupported_capabilities: string[];
}

export interface NetworkBoundaryPolicy {
  esp32_ap_ssid: string;
  esp32_dashboard_url: string;
  esp32_mjpeg_stream_url: string;
  direct_cloud_probe_allowed: boolean;
  gateway_status: "not_deployed_phase_4" | "connected" | "offline";
  explanation: string;
}

export interface AICapabilityPolicy {
  inference_enabled: boolean;
  active_model_profile: string;
  first_working_workflow: string;
  model_honesty_notice: string;
  validated_target_classes: string[];
  requires_custom_training_for: string[];
}

export interface ModuleReadinessItem {
  id: string;
  name: string;
  route: string;
  phase: string;
  status: "foundation_active" | "schema_ready" | "planned";
  summary: string;
}

export interface CapabilitiesResponse {
  hardware_baseline: HardwareDeviceSpec[];
  network_boundary: NetworkBoundaryPolicy;
  ai_policy: AICapabilityPolicy;
  modules: ModuleReadinessItem[];
}

export interface GeoJsonPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface FieldCreate {
  name: string;
  code: string;
  description?: string | null;
  location?: string | null;
  crop_type?: string | null;
  area_hectares?: number | null;
  boundary_geojson?: GeoJsonPolygon | null;
  notes?: string | null;
}

export interface FieldUpdate {
  name?: string;
  code?: string;
  description?: string | null;
  location?: string | null;
  crop_type?: string | null;
  area_hectares?: number | null;
  boundary_geojson?: GeoJsonPolygon | null;
  clear_boundary?: boolean;
  notes?: string | null;
}

export interface FieldRead {
  id: string;
  owner_id: string | null;
  name: string;
  code: string;
  description: string | null;
  location: string | null;
  crop_type: string | null;
  area_hectares: number | null;
  boundary_geojson: GeoJsonPolygon | null;
  centroid_lat: number | null;
  centroid_lng: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type DeviceType = "camera_module" | "airframe" | "edge_gateway" | "sensor_node";
export type ConnectivityMode = "isolated_ap" | "manual_import" | "edge_gateway";
export type DeviceStatus =
  | "registered"
  | "offline_isolated_ap"
  | "awaiting_gateway"
  | "maintenance"
  | "decommissioned";

export interface DeviceCreate {
  name: string;
  device_type: DeviceType;
  device_identifier: string;
  hardware_model: string;
  assigned_field_id?: string | null;
  connectivity_mode?: ConnectivityMode;
  status?: DeviceStatus;
  local_ssid?: string | null;
  local_endpoint_url?: string | null;
  connection_config?: Record<string, unknown>;
  capabilities?: Record<string, unknown>;
  notes?: string | null;
}

export interface DeviceUpdate {
  name?: string;
  device_type?: DeviceType;
  device_identifier?: string;
  hardware_model?: string;
  assigned_field_id?: string | null;
  unassign_field?: boolean;
  connectivity_mode?: ConnectivityMode;
  status?: DeviceStatus;
  local_ssid?: string | null;
  local_endpoint_url?: string | null;
  connection_config?: Record<string, unknown>;
  capabilities?: Record<string, unknown>;
  notes?: string | null;
}

export interface DeviceRead {
  id: string;
  owner_id: string | null;
  assigned_field_id: string | null;
  name: string;
  device_type: string;
  device_identifier: string | null;
  hardware_model: string;
  connectivity_mode: string;
  status: string;
  local_ssid: string | null;
  local_endpoint_url: string | null;
  connection_config: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  notes: string | null;
  last_seen_at: string | null;
  last_authenticated_contact_at: string | null;
  created_at: string;
  updated_at: string;
}

export type MissionStatus = "draft" | "planned" | "in_progress" | "completed" | "cancelled";

export interface MissionObservation {
  id: string;
  author_id: string | null;
  author_name: string;
  note: string;
  recorded_at: string;
}

export interface MissionCreate {
  title: string;
  description?: string | null;
  field_id?: string | null;
  device_id?: string | null;
  status?: "draft" | "planned";
  operator_notes?: string | null;
  metadata_json?: Record<string, unknown>;
}

export interface MissionUpdate {
  title?: string;
  description?: string | null;
  field_id?: string | null;
  unassign_field?: boolean;
  device_id?: string | null;
  unassign_device?: boolean;
  operator_notes?: string | null;
  metadata_json?: Record<string, unknown>;
}

export interface MissionRead {
  id: string;
  owner_id: string | null;
  field_id: string | null;
  device_id: string | null;
  operator_id: string | null;
  title: string;
  description: string | null;
  status: MissionStatus;
  started_at: string | null;
  completed_at: string | null;
  operator_notes: string | null;
  observations: MissionObservation[];
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MediaAssetRead {
  id: string;
  mission_id: string | null;
  field_id: string | null;
  uploaded_by: string | null;
  media_type: "image" | "video" | string;
  upload_status: string;
  storage_backend: string;
  storage_key: string;
  safe_filename: string | null;
  original_filename: string;
  mime_type: string;
  byte_size: number;
  sha256: string;
  width_px: number | null;
  height_px: number | null;
  captured_at: string | null;
  geo_lat: number | null;
  geo_lng: number | null;
  geo_source: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface MediaDownloadUrlResponse {
  media_id: string;
  storage_backend: string;
  url: string;
  expires_in_seconds: number | null;
  filename: string;
}

export type DetectionMode = "general" | "wildlife" | "pest" | "disease";
export type DetectionJobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";
export type ReviewStatus = "unreviewed" | "confirmed" | "rejected" | "uncertain";

export interface ModelEvaluationSummary {
  dataset_name: string;
  dataset_version: string;
  train_images: number;
  val_images: number;
  test_images: number;
  precision: number | null;
  recall: number | null;
  map50: number | null;
  map50_95: number | null;
  notes: string;
}

export interface ModelRegistryItem {
  model_id: string;
  name: string;
  version: string;
  detection_mode: DetectionMode;
  architecture: string;
  license_spdx: string;
  dataset_scope: string;
  status: "available" | "not_available";
  status_reason: string;
  weights_filename: string;
  expected_sha256: string | null;
  actual_sha256: string | null;
  supported_classes: string[];
  total_class_count: number;
  default_confidence: number;
  is_specialized_agricultural: boolean;
  honesty_disclaimer: string;
  evaluation: ModelEvaluationSummary | null;
  requirements_for_activation: string[];
}

export interface DetectionJobCreateRequest {
  media_asset_id: string;
  model_id: string;
  confidence_threshold: number;
  frame_sample_interval_ms?: number;
  max_frames?: number;
  run_async?: boolean;
}

export interface DetectionItemRead {
  id: string;
  job_id: string;
  class_id: number | null;
  label: string;
  confidence: number;
  original_label: string | null;
  original_confidence: number | null;
  bbox_x1: number;
  bbox_y1: number;
  bbox_x2: number;
  bbox_y2: number;
  frame_index: number;
  timestamp_ms: number | null;
  annotated_frame_storage_key: string | null;
  review_status: ReviewStatus;
  reviewer_id: string | null;
  reviewed_at: string | null;
  reviewer_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface DetectionItemReviewRequest {
  review_status: ReviewStatus;
  reviewer_notes?: string | null;
  corrected_label?: string | null;
}

export interface DetectionJobSummary {
  analysis_type?: "still_image" | "sampled_video" | string;
  sampling_mode?: string;
  sampling_notice?: string;
  total_detections?: number;
  class_counts?: Record<string, number>;
  average_confidence?: number | null;
  width_px?: number;
  height_px?: number;
  total_video_frames?: number;
  total_frames_sampled?: number;
  frame_sample_interval_ms?: number;
  video_duration_ms?: number;
  sampled_frames?: Array<{
    frame_index: number;
    raw_frame_index: number;
    timestamp_ms: number;
    detection_count: number;
  }>;
  review_counts?: {
    unreviewed: number;
    confirmed: number;
    rejected: number;
    uncertain: number;
  };
  attempts?: number;
  retry_count?: number;
}

export interface DetectionJobRead {
  id: string;
  owner_id: string | null;
  field_id: string | null;
  mission_id: string | null;
  media_asset_id: string;
  detection_mode: string;
  model_id: string;
  status: DetectionJobStatus;
  progress_percent: number;
  media_type: "image" | "video" | string;
  model_name: string;
  model_version: string;
  model_checksum: string | null;
  dataset_scope: string;
  device_used: string;
  confidence_threshold: number;
  frame_sample_interval_ms: number | null;
  max_frames: number | null;
  total_frames_sampled: number | null;
  video_duration_ms: number | null;
  annotated_storage_key: string | null;
  summary_json: DetectionJobSummary;
  inference_ms: number | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DetectionJobDetailRead extends DetectionJobRead {
  items: DetectionItemRead[];
  media_asset: MediaAssetRead | null;
}

export interface DatasetRead {
  id: string;
  owner_id: string | null;
  name: string;
  version: string;
  detection_mode: string;
  classes_json: string[];
  train_count: number;
  val_count: number;
  test_count: number;
  metrics_json: Record<string, unknown>;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertRead {
  id: string;
  field_id: string | null;
  device_id: string | null;
  detection_job_id: string | null;
  severity: string;
  category: string;
  title: string;
  message: string;
  status: string;
  acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
}

export type GatewayDeploymentMode = "local_dev" | "remote_cloud";

export interface GatewayRead {
  id: string;
  owner_id: string | null;
  device_id: string | null;
  name: string;
  gateway_identifier: string;
  deployment_mode: GatewayDeploymentMode | string;
  credential_prefix: string;
  credential_version: number;
  status: "enrolled" | "active" | "revoked" | string;
  is_live: boolean;
  heartbeat_age_seconds: number | null;
  camera_reachable: boolean;
  camera_fps: number | null;
  dropped_frames: number;
  queue_depth: number;
  queue_bytes: number;
  internet_reachable: boolean | null;
  local_interface: string | null;
  uplink_interface: string | null;
  diagnostics_json: Record<string, unknown>;
  last_heartbeat_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GatewayEnrollRequest {
  name: string;
  gateway_identifier: string;
  device_id?: string | null;
  deployment_mode?: GatewayDeploymentMode;
}

export interface GatewayEnrollResponse {
  gateway: GatewayRead;
  gateway_token: string;
}

export interface StreamSessionRead {
  id: string;
  gateway_id: string;
  device_id: string | null;
  status: "active" | "stopped" | "expired" | string;
  target_fps: number;
  max_frame_bytes: number;
  frames_relayed: number;
  expires_at: string;
  stopped_at: string | null;
  last_frame_at: string | null;
  created_at: string;
}

export interface GatewayDiagnosticsResponse {
  gateway: GatewayRead;
  active_session: StreamSessionRead | null;
  heartbeat_ttl_seconds: number;
  network_guidance: string;
  esp32_ap_ssid: string;
  esp32_local_url: string;
  esp32_stream_url: string;
  direct_cloud_probe_allowed: boolean;
}

// Phase 5 Smart Analytics, Alerts, Notifications & Reporting

export type AlertSeverity = "info" | "warning" | "critical";
export type AlertTriggerType =
  | "yolo_class_detected"
  | "confidence_threshold_reached"
  | "human_confirmed_detection"
  | "ai_analysis_failed"
  | "gateway_offline_ttl"
  | "mission_status_changed";
export type AlertStatus = "open" | "acknowledged" | "resolved";
export type ReportType =
  | "field_analysis"
  | "mission_summary"
  | "ai_detection"
  | "device_activity"
  | "alert_history";
export type ReportFormat = "pdf" | "csv" | "json";

export interface AnalyticsJobsSummary {
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  active_or_queued_jobs: number;
  cancelled_jobs: number;
  avg_inference_ms: number | null;
}

export interface AnalyticsDetectionsSummary {
  raw_detection_items: number;
  unique_job_class_occurrences: number;
  human_confirmed_count: number;
  human_rejected_count: number;
  human_uncertain_count: number;
  unreviewed_count: number;
}

export interface ClassDistributionItem {
  label: string;
  raw_count: number;
  unique_job_count: number;
  confirmed_count: number;
  avg_confidence: number;
}

export interface ConfidenceBucketItem {
  bucket_label: string;
  min_score: number;
  max_score: number;
  count: number;
}

export interface DetectionTrendPoint {
  date: string;
  jobs_completed: number;
  jobs_failed: number;
  raw_detections: number;
  unique_job_class_occurrences: number;
  confirmed_detections: number;
}

export interface FieldAnalyticsSummary {
  field_id: string;
  field_name: string;
  code: string;
  crop_type: string | null;
  area_hectares: number | null;
  missions_count: number;
  jobs_count: number;
  completed_jobs: number;
  raw_detections: number;
  unique_job_class_occurrences: number;
  confirmed_detections: number;
}

export interface MissionAnalyticsSummary {
  mission_id: string;
  title: string;
  status: string;
  field_id: string | null;
  field_name: string | null;
  jobs_count: number;
  completed_jobs: number;
  raw_detections: number;
  unique_job_class_occurrences: number;
  confirmed_detections: number;
  updated_at: string;
}

export interface AlertSeveritySummaryItem {
  severity: string;
  count: number;
}

export interface ConnectivityEventItem {
  id: string;
  event_type: string;
  camera_reachable: boolean;
  internet_reachable: boolean | null;
  camera_fps: number | null;
  dropped_frames: number;
  detail: string | null;
  created_at: string;
}

export interface DeviceConnectivitySummary {
  gateway_id: string;
  gateway_name: string;
  gateway_identifier: string;
  device_id: string | null;
  device_name: string | null;
  current_status: string;
  last_heartbeat_at: string | null;
  total_events: number;
  offline_events: number;
  recent_events: ConnectivityEventItem[];
}

export interface AnalyticsOverviewResponse {
  generated_at: string;
  date_from: string | null;
  date_to: string | null;
  field_id: string | null;
  mission_id: string | null;
  methodology_note: string;
  jobs_summary: AnalyticsJobsSummary;
  detections_summary: AnalyticsDetectionsSummary;
  class_distribution: ClassDistributionItem[];
  confidence_distribution: ConfidenceBucketItem[];
  detection_trends: DetectionTrendPoint[];
  field_summaries: FieldAnalyticsSummary[];
  mission_summaries: MissionAnalyticsSummary[];
  alert_severity_distribution: AlertSeveritySummaryItem[];
  open_alerts: number;
  acknowledged_alerts: number;
  resolved_alerts: number;
  device_connectivity: DeviceConnectivitySummary[];
}

export interface VerifiedMapDetectionPoint {
  media_asset_id: string;
  original_filename: string;
  field_id: string | null;
  mission_id: string | null;
  geo_lat: number;
  geo_lng: number;
  geo_source: string;
  detection_count: number;
  confirmed_count: number;
  captured_at: string | null;
}

export interface MapFieldSummary {
  field_id: string;
  name: string;
  code: string;
  crop_type: string | null;
  area_hectares: number | null;
  centroid_lat: number | null;
  centroid_lng: number | null;
  boundary_geojson: GeoJsonPolygon | null;
  missions_count: number;
  jobs_count: number;
  raw_detections: number;
  unique_job_class_occurrences: number;
  confirmed_detections: number;
}

export interface MapAnalyticsResponse {
  generated_at: string;
  gps_telemetry_available: boolean;
  gps_honesty_note: string;
  fields: MapFieldSummary[];
  verified_detection_points: VerifiedMapDetectionPoint[];
}

export interface AlertRuleCreate {
  name: string;
  description?: string | null;
  enabled?: boolean;
  severity: AlertSeverity;
  trigger_type: AlertTriggerType;
  target_classes?: string[];
  min_confidence?: number | null;
  target_mission_statuses?: string[];
  field_id?: string | null;
  device_id?: string | null;
  cooldown_minutes?: number;
}

export interface AlertRuleRead {
  id: string;
  owner_id: string | null;
  name: string;
  description: string | null;
  enabled: boolean;
  severity: AlertSeverity;
  trigger_type: AlertTriggerType;
  target_classes: string[];
  min_confidence: number | null;
  target_mission_statuses: string[];
  field_id: string | null;
  device_id: string | null;
  cooldown_minutes: number;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertPhase5Read {
  id: string;
  owner_id: string | null;
  rule_id: string | null;
  field_id: string | null;
  device_id: string | null;
  mission_id: string | null;
  gateway_id: string | null;
  detection_job_id: string | null;
  severity: AlertSeverity;
  category: string;
  title: string;
  message: string;
  status: AlertStatus;
  dedupe_key: string | null;
  metadata_json: Record<string, unknown>;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationRead {
  id: string;
  user_id: string;
  alert_id: string | null;
  severity: AlertSeverity;
  title: string;
  message: string;
  link_path: string | null;
  is_read: boolean;
  read_at: string | null;
  channel: string;
  delivery_status: string;
  created_at: string;
  updated_at: string;
}

export interface NotificationPreferenceRead {
  in_app_enabled: boolean;
  email_enabled: boolean;
  email_address: string | null;
  min_severity: AlertSeverity;
  muted_trigger_types: string[];
  email_available: boolean;
  email_status_reason: string;
}

export interface ReportPreviewResponse {
  report_type: ReportType;
  title: string;
  generated_at: string;
  generated_by_email: string;
  date_from: string | null;
  date_to: string | null;
  field_id: string | null;
  mission_id: string | null;
  summary_metrics: Record<string, unknown>;
  model_provenance: Array<Record<string, unknown>>;
  human_review_status: Record<string, number>;
  methodological_limitations: string[];
  rows: Array<Record<string, unknown>>;
}

export type CameraType = "ENTRY" | "EXIT";

export interface Camera {
  id: number;
  name: string;
  rtsp_url: string;
  camera_type: CameraType;
  location: string | null;
  description: string | null;
  is_active: boolean;
  // null = inherit the global CAMERA_FPS setting (Settings page).
  // 1..30 = per-camera override.
  fps_override: number | null;
  created_at: string;
  updated_at: string;
  // Set by create/update/smart-connect when the DB row saved but the
  // worker could not be started (H9). Frontend surfaces a warning toast.
  worker_warning?: string | null;
}

export interface CameraCreate {
  name: string;
  rtsp_url: string;
  camera_type: CameraType;
  location?: string | null;
  description?: string | null;
  is_active?: boolean;
  fps_override?: number | null;
}

export interface CameraUpdate {
  name?: string;
  rtsp_url?: string;
  camera_type?: CameraType;
  location?: string | null;
  description?: string | null;
  is_active?: boolean;
  fps_override?: number | null;
}

export interface CameraHealth {
  id: number;
  name: string;
  is_active: boolean;
  is_running: boolean;
  last_heartbeat_age_seconds: number | null;
  // null until a frame actually arrives. Use this — NOT
  // last_heartbeat_age_seconds — to decide whether the camera is "Live".
  last_frame_age_seconds: number | null;
  seconds_since_start: number | null;
  processed_frames: number;
  consecutive_open_failures: number;
  consecutive_read_failures: number;
  total_reconnects: number;
  // One of: CONNECTING, STREAMING, FLAPPING, DEGRADED, STOPPED, UNKNOWN
  health_state: string;
  fps_effective: number | null;
  fps_override: number | null;
  // Native FPS auto-detected from the RTSP stream. Null until first
  // successful open. Tells the operator what the camera actually delivers
  // (vs. what was configured).
  fps_detected: number | null;
  lifetime_restarts: number;
  last_error: string | null;
}

export interface CameraProbeRequest {
  rtsp_url: string;
  timeout_ms?: number;
}

export interface CameraProbeResult {
  ok: boolean;
  width: number | null;
  height: number | null;
  elapsed_ms: number;
  error: string | null;
}

// -----------------------------------------------------------------------
// Smart Connect — the bulletproof RTSP connector
// -----------------------------------------------------------------------

export interface SmartConnectRequest {
  name: string;
  camera_type: CameraType;
  location?: string | null;
  description?: string | null;
  is_active?: boolean;
  fps_override?: number | null;
  // Either rtsp_url, or host + username + password (or both — URL preferred).
  rtsp_url?: string | null;
  host?: string | null;
  port?: number;
  username?: string | null;
  password?: string | null;
  prefer_sub_stream?: boolean;
  probe_timeout_seconds?: number;
}

export interface SmartProbeStep {
  name: string;
  ok: boolean;
  duration_ms: number;
  detail: string;
  error: string | null;
}

export interface SmartProbeResult {
  ok: boolean;
  working_url: string | null;
  width: number | null;
  height: number | null;
  strategy: string; // "user_url" | "onvif_discovery" | "vendor_fallback" | ...
  vendor_hint: string | null;
  steps: SmartProbeStep[];
  summary: string;
  suggestion: string | null;
}

export interface SmartConnectResult {
  camera: Camera | null;
  probe: SmartProbeResult;
}

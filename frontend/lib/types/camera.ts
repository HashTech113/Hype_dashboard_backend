export type CameraType = "ENTRY" | "EXIT";

export interface Camera {
  id: number;
  name: string;
  rtsp_url: string;
  camera_type: CameraType;
  location: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CameraCreate {
  name: string;
  rtsp_url: string;
  camera_type: CameraType;
  location?: string | null;
  description?: string | null;
  is_active?: boolean;
}

export interface CameraUpdate {
  name?: string;
  rtsp_url?: string;
  camera_type?: CameraType;
  location?: string | null;
  description?: string | null;
  is_active?: boolean;
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
  processed_frames: number;
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

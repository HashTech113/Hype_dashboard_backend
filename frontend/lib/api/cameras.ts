import { api } from "@/lib/api/client";
import type {
  Camera,
  CameraCreate,
  CameraHealth,
  CameraProbeRequest,
  CameraProbeResult,
  CameraUpdate,
  SmartConnectRequest,
  SmartConnectResult,
  SmartProbeResult,
} from "@/lib/types/camera";

export const camerasApi = {
  list: () => api.get<Camera[]>("/cameras"),

  get: (id: number) => api.get<Camera>(`/cameras/${id}`),

  health: () => api.get<CameraHealth[]>("/cameras/health"),

  create: (payload: CameraCreate) => api.post<Camera>("/cameras", payload),

  update: (id: number, payload: CameraUpdate) =>
    api.patch<Camera>(`/cameras/${id}`, payload),

  remove: (id: number) => api.delete<void>(`/cameras/${id}`),

  restart: (id: number) => api.post<void>(`/cameras/${id}/restart`),

  probe: (payload: CameraProbeRequest) =>
    api.post<CameraProbeResult>(
      "/cameras/probe",
      {
        rtsp_url: payload.rtsp_url,
        timeout_ms: payload.timeout_ms ?? 5000,
      },
      // The backend probe waits up to timeout_ms; give axios headroom on top.
      { timeout: (payload.timeout_ms ?? 5000) + 5000 },
    ),

  // Smart Connect — run the discovery ladder without persisting.
  // Backend probe walks up to 22 vendor candidates; worst case ~45s for a
  // camera that times out on every path. Give axios 60s headroom so the
  // operator sees the precise step-by-step diagnostic instead of an opaque
  // "request timed out" from the HTTP client.
  smartProbe: (payload: SmartConnectRequest) =>
    api.post<SmartProbeResult>("/cameras/smart-probe", payload, {
      timeout: 60_000,
    }),

  // Smart Connect — run the ladder AND persist the camera if a working URL is found.
  connectSmart: (payload: SmartConnectRequest) =>
    api.post<SmartConnectResult>("/cameras/connect-smart", payload, {
      timeout: 60_000,
    }),

  // WebRTC stream info — returns 503 if go2rtc isn't running (frontend
  // falls back to WebSocket JPEG). 200 returns the signalling URL the
  // browser uses to negotiate WebRTC with go2rtc.
  webrtcInfo: (cameraId: number) =>
    api.get<{
      name: string;
      webrtc_url: string;
      mse_url: string;
      mjpeg_url: string;
    }>(`/cameras/${cameraId}/webrtc-info`),

  // LAN auto-discovery — ONVIF WS-Discovery multicast + TCP scan of local
  // /24 subnets. Returns devices found with vendor hint where available.
  // Operator clicks one to launch Smart Connect with the IP pre-filled.
  //
  // Timeout budget on the BACKEND:
  //   ~4s    ONVIF WS-Discovery multicast (sock.settimeout)
  //   ~12-20s TCP scan of each detected /24 subnet at 0.3s probe timeout
  //           with 128 parallel workers (more interfaces = longer)
  //   ~2s    extra for slow-responding 80/8000 port checks on each hit
  // Worst case on a multi-NIC dev box: ~30s. Give axios 90s headroom
  // so the operator NEVER sees "Request timed out" while the backend is
  // still working — the backend's own 90s safety cutoff returns whatever
  // it has by then.
  discover: () =>
    api.post<{
      count: number;
      cameras: Array<{
        ip: string;
        source: "onvif" | "tcp_scan";
        onvif_url: string | null;
        rtsp_port: number;
        web_port: number;
        vendor_hint: string | null;
        notes: string[];
      }>;
    }>("/cameras/discover", undefined, { timeout: 90_000 }),

  previewBlob: (
    id: number,
    opts: { annotated?: boolean; maxAgeSeconds?: number; quality?: number } = {},
  ) =>
    api.get<Blob>(`/cameras/${id}/preview.jpg`, {
      responseType: "blob",
      params: {
        annotated: opts.annotated ?? true,
        max_age_seconds: opts.maxAgeSeconds ?? 10,
        quality: opts.quality ?? 80,
      },
    }),
};

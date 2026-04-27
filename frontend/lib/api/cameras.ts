import { api } from "@/lib/api/client";
import type {
  Camera,
  CameraCreate,
  CameraHealth,
  CameraProbeRequest,
  CameraProbeResult,
  CameraUpdate,
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
    api.post<CameraProbeResult>("/cameras/probe", {
      rtsp_url: payload.rtsp_url,
      timeout_ms: payload.timeout_ms ?? 5000,
    }),

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

"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { camerasApi } from "@/lib/api/cameras";
import type {
  CameraCreate,
  CameraProbeRequest,
  CameraUpdate,
} from "@/lib/types/camera";

export const cameraKeys = {
  all: ["cameras"] as const,
  list: ["cameras", "list"] as const,
  detail: (id: number) => ["cameras", "detail", id] as const,
  health: ["cameras", "health"] as const,
};

function toastError(err: unknown, fallback: string) {
  const msg = err instanceof ApiError ? err.message : fallback;
  toast.error(msg);
}

export function useCameras() {
  return useQuery({
    queryKey: cameraKeys.list,
    queryFn: () => camerasApi.list(),
  });
}

export function useCamera(id: number | null) {
  return useQuery({
    queryKey: id ? cameraKeys.detail(id) : ["cameras", "detail", "none"],
    queryFn: () => camerasApi.get(id as number),
    enabled: id !== null,
  });
}

export function useCamerasHealth(refetchMs: number | false = 5_000) {
  return useQuery({
    queryKey: cameraKeys.health,
    queryFn: () => camerasApi.health(),
    refetchInterval: refetchMs === false ? undefined : refetchMs,
  });
}

export function useCreateCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CameraCreate) => camerasApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cameraKeys.all });
      toast.success("Camera added");
    },
    onError: (err) => toastError(err, "Could not add camera"),
  });
}

export function useUpdateCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: CameraUpdate }) =>
      camerasApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cameraKeys.all });
      toast.success("Camera updated");
    },
    onError: (err) => toastError(err, "Could not update camera"),
  });
}

export function useDeleteCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => camerasApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cameraKeys.all });
      toast.success("Camera removed");
    },
    onError: (err) => toastError(err, "Could not remove camera"),
  });
}

export function useRestartCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => camerasApi.restart(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cameraKeys.health });
      toast.success("Camera restarted");
    },
    onError: (err) => toastError(err, "Could not restart camera"),
  });
}

export function useProbeCamera() {
  return useMutation({
    mutationFn: (payload: CameraProbeRequest) => camerasApi.probe(payload),
    onError: (err) => toastError(err, "Probe failed"),
  });
}

/**
 * Polls a camera's annotated preview JPEG and exposes a stable object
 * URL the consumer can drop into <img src=...>. Revokes the previous
 * URL whenever a fresh frame lands so the browser's blob memory is bounded.
 *
 * - `intervalMs`: poll cadence (default 600 ms — tuned for camera_fps=5).
 *   Lower than the camera's frame interval just gives duplicate frames; we
 *   keep it tight so users get a near-realtime feel.
 * - On error, the last good frame is kept on screen and `error` is set;
 *   polling continues so the view recovers automatically.
 */
export function useCameraPreview(
  cameraId: number | null,
  intervalMs: number = 600,
) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const currentUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (cameraId === null) {
      setUrl(null);
      setError(null);
      setUpdatedAt(null);
      return;
    }
    let active = true;

    async function tick() {
      if (!active || cameraId === null) return;
      try {
        const blob = await camerasApi.previewBlob(cameraId);
        if (!active) return;
        const next = URL.createObjectURL(blob);
        if (currentUrlRef.current) {
          URL.revokeObjectURL(currentUrlRef.current);
        }
        currentUrlRef.current = next;
        setUrl(next);
        setUpdatedAt(Date.now());
        setError(null);
      } catch (err) {
        if (!active) return;
        const msg =
          err instanceof ApiError
            ? err.status === 404
              ? "No frame yet"
              : err.message
            : "Failed to load preview";
        setError(msg);
      }
    }

    void tick();
    const handle = window.setInterval(() => void tick(), intervalMs);

    return () => {
      active = false;
      window.clearInterval(handle);
      if (currentUrlRef.current) {
        URL.revokeObjectURL(currentUrlRef.current);
        currentUrlRef.current = null;
      }
      setUrl(null);
    };
  }, [cameraId, intervalMs]);

  return { url, error, updatedAt };
}

"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { unknownsApi } from "@/lib/api/unknowns";
import type {
  PromoteToNewPayload,
  UnknownClusterListParams,
} from "@/lib/types/unknowns";

export const unknownKeys = {
  all: ["unknowns"] as const,
  list: (params: UnknownClusterListParams) =>
    ["unknowns", "list", params] as const,
  detail: (id: number) => ["unknowns", "detail", id] as const,
  capture: (id: number) => ["unknowns", "capture", id] as const,
  // Shared blob cache (H12) — same captureId across multiple components
  // resolves to the same ObjectURL fetched once.
  captureBlob: (id: number) => ["unknowns", "capture-blob", id] as const,
};

function toastError(err: unknown, fallback: string) {
  const msg = err instanceof ApiError ? err.message : fallback;
  toast.error(msg);
}

export function useUnknownClusterList(
  params: UnknownClusterListParams,
  refetchMs: number | false = 30_000,
) {
  return useQuery({
    queryKey: unknownKeys.list(params),
    queryFn: () => unknownsApi.list(params),
    placeholderData: (prev) => prev,
    refetchInterval: refetchMs === false ? undefined : refetchMs,
  });
}

export function useUnknownCluster(id: number | null) {
  return useQuery({
    queryKey: id ? unknownKeys.detail(id) : ["unknowns", "detail", "none"],
    queryFn: () => unknownsApi.get(id as number),
    enabled: id !== null,
  });
}

/**
 * Fetches a face capture image as an authenticated blob and exposes it as a
 * stable object URL for <img>. Mirrors `useSnapshotUrl` from attendance.
 *
 * H12 fix: now uses useQuery so the same captureId is fetched once and
 * shared across every card on the grid + the detail dialog. Previously a
 * page of 24 cards issued 24 independent auth fetches, queued at Chrome's
 * 6-per-origin cap, and re-fetched everything on every re-render.
 *
 * The ObjectURL is created INSIDE queryFn and stored in the cache, so all
 * consumers get the same URL string (cheap, stable). When the query is
 * garbage-collected after gcTime, we revoke the URL via the queryCache
 * listener installed in providers.tsx — see `installBlobRevocation`.
 */
export function useUnknownCaptureUrl(captureId: number | null | undefined) {
  const q = useQuery({
    queryKey: captureId
      ? unknownKeys.captureBlob(captureId)
      : ["unknowns", "capture-blob", "none"],
    queryFn: async () => {
      if (!captureId) return null;
      const blob = await unknownsApi.captureBlob(captureId);
      return URL.createObjectURL(blob);
    },
    enabled: !!captureId,
    staleTime: 10 * 60_000, // 10 min — images don't change once written
    gcTime: 15 * 60_000,
  });
  return {
    url: (q.data as string | null) ?? null,
    loading: q.isLoading,
    error: q.error
      ? (q.error instanceof Error ? q.error.message : "Failed to load image")
      : null,
  };
}

export function useSetClusterLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, label }: { id: number; label: string | null }) =>
      unknownsApi.setLabel(id, label),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: unknownKeys.all });
      qc.invalidateQueries({ queryKey: unknownKeys.detail(id) });
      toast.success("Label saved");
    },
    onError: (err) => toastError(err, "Could not save label"),
  });
}

export function useDiscardCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unknownsApi.discard(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: unknownKeys.all });
      toast.success("Cluster discarded");
    },
    onError: (err) => toastError(err, "Could not discard cluster"),
  });
}

export function usePromoteToNewEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      clusterId,
      payload,
    }: {
      clusterId: number;
      payload: PromoteToNewPayload;
    }) => unknownsApi.promoteNew(clusterId, payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: unknownKeys.all });
      qc.invalidateQueries({ queryKey: ["employees"] });
      toast.success(
        `${res.employee_name} added • ${res.captures_promoted} face image${
          res.captures_promoted === 1 ? "" : "s"
        } enrolled`,
      );
    },
    onError: (err) => toastError(err, "Could not add as employee"),
  });
}

export function usePromoteToExistingEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      clusterId,
      employeeId,
    }: {
      clusterId: number;
      employeeId: number;
    }) => unknownsApi.promoteExisting(clusterId, employeeId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: unknownKeys.all });
      qc.invalidateQueries({ queryKey: ["employees"] });
      toast.success(
        `Added ${res.captures_promoted} face image${
          res.captures_promoted === 1 ? "" : "s"
        } to ${res.employee_name}`,
      );
    },
    onError: (err) => toastError(err, "Could not append to existing employee"),
  });
}

export function useRecluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { min_cluster_size?: number; min_samples?: number } = {}) =>
      unknownsApi.recluster(params),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: unknownKeys.all });
      if (!res.ran) {
        toast.info("Re-cluster: nothing to do (no pending clusters)");
        return;
      }
      const msg =
        res.clusters_merged === 0
          ? `Re-cluster done: no drift found (${res.captures_total} captures)`
          : `Re-cluster done: ${res.clusters_merged} cluster${
              res.clusters_merged === 1 ? "" : "s"
            } merged, ${res.captures_migrated} capture${
              res.captures_migrated === 1 ? "" : "s"
            } moved`;
      toast.success(msg);
    },
    onError: (err) => toastError(err, "Re-cluster failed"),
  });
}

export function usePurgeUnknowns() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      max_age_days?: number | null;
      include_promoted?: boolean;
    } = {}) => unknownsApi.purge(params),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: unknownKeys.all });
      const mb = (res.bytes_freed / (1024 * 1024)).toFixed(1);
      toast.success(
        `Purged ${res.clusters_deleted} cluster${
          res.clusters_deleted === 1 ? "" : "s"
        } • ${res.files_deleted} files (${mb} MB)`,
      );
    },
    onError: (err) => toastError(err, "Purge failed"),
  });
}

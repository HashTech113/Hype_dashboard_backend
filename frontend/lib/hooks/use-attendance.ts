"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import {
  attendanceApi,
  type EventUpdatePayload,
  type ManualEventCreate,
} from "@/lib/api/attendance";
import type { EventListParams } from "@/lib/types/attendance";

export const attendanceKeys = {
  all: ["attendance"] as const,
  events: (params: EventListParams) =>
    ["attendance", "events", "detailed", params] as const,
  snapshot: (eventId: number) =>
    ["attendance", "snapshot", eventId] as const,
};

function toastError(err: unknown, fallback: string) {
  const msg = err instanceof ApiError ? err.message : fallback;
  toast.error(msg);
}

export function useEventList(params: EventListParams) {
  return useQuery({
    queryKey: attendanceKeys.events(params),
    queryFn: () => attendanceApi.listDetailed(params),
    placeholderData: (prev) => prev,
    refetchInterval: 15_000,
  });
}

export function useSnapshotUrl(eventId: number | null | undefined) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) {
      setUrl(null);
      setError(null);
      return;
    }
    let active = true;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);

    attendanceApi
      .snapshotBlob(eventId)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load snapshot");
        setUrl(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [eventId]);

  return { url, loading, error };
}

export function useCreateManualEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ManualEventCreate) => attendanceApi.createEvent(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      toast.success("Event added");
    },
    onError: (err) => toastError(err, "Could not add event"),
  });
}

export function useUpdateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId: number;
      payload: EventUpdatePayload;
    }) => attendanceApi.updateEvent(eventId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      toast.success("Event updated");
    },
    onError: (err) => toastError(err, "Could not update event"),
  });
}

export function useDeleteEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (eventId: number) => attendanceApi.deleteEvent(eventId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      toast.success("Event deleted");
    },
    onError: (err) => toastError(err, "Could not delete event"),
  });
}

export function useRecomputeDay() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      workDate,
      employeeId,
    }: {
      workDate: string;
      employeeId?: number;
    }) => attendanceApi.recomputeDay(workDate, employeeId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      toast.success(`Recomputed ${res.touched} rollup${res.touched === 1 ? "" : "s"}`);
    },
    onError: (err) => toastError(err, "Recompute failed"),
  });
}

export function useRecomputeRange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      startDate,
      endDate,
      employeeId,
    }: {
      startDate: string;
      endDate: string;
      employeeId?: number;
    }) => attendanceApi.recomputeRange(startDate, endDate, employeeId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      toast.success(`Recomputed ${res.touched} rollup${res.touched === 1 ? "" : "s"}`);
    },
    onError: (err) => toastError(err, "Recompute failed"),
  });
}

export function useCloseDay() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (workDate: string) => attendanceApi.closeDay(workDate),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: attendanceKeys.all });
      toast.success(
        `Day closed: ${res.closed} updated, ${res.already_closed} already, ${res.no_activity} no activity`,
      );
    },
    onError: (err) => toastError(err, "Close day failed"),
  });
}

"use client";

import { useQuery } from "@tanstack/react-query";

import { dashboardApi } from "@/lib/api/dashboard";

export const dashboardKeys = {
  snapshot: ["dashboard", "snapshot"] as const,
  timeline: (limit: number, offset: number) =>
    ["dashboard", "timeline", limit, offset] as const,
  eventsByHour: (hours: number) =>
    ["dashboard", "events-by-hour", hours] as const,
};

export function useDashboardSnapshot(refetchMs: number = 15_000) {
  return useQuery({
    queryKey: dashboardKeys.snapshot,
    queryFn: () => dashboardApi.snapshot(),
    refetchInterval: refetchMs,
  });
}

export function useTimeline(
  limit: number = 25,
  offset: number = 0,
  refetchMs: number = 10_000,
) {
  return useQuery({
    queryKey: dashboardKeys.timeline(limit, offset),
    queryFn: () => dashboardApi.timeline(limit, offset),
    refetchInterval: refetchMs,
  });
}

export function useEventsByHour(hours: number = 24, refetchMs: number = 60_000) {
  return useQuery({
    queryKey: dashboardKeys.eventsByHour(hours),
    queryFn: () => dashboardApi.eventsByHour(hours),
    refetchInterval: refetchMs,
  });
}

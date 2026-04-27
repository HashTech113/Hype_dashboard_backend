"use client";

import { useQuery } from "@tanstack/react-query";

import { presenceApi } from "@/lib/api/presence";

export const presenceKeys = {
  list: ["presence", "list"] as const,
};

export function usePresence(refetchMs: number = 10_000) {
  return useQuery({
    queryKey: presenceKeys.list,
    queryFn: () => presenceApi.list(),
    refetchInterval: refetchMs,
  });
}

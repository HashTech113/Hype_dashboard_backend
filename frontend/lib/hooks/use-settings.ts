"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { settingsApi } from "@/lib/api/settings";
import type { SettingsUpdate } from "@/lib/types/settings";

export const settingsKeys = {
  current: ["settings", "current"] as const,
};

export function useSettings() {
  return useQuery({
    queryKey: settingsKeys.current,
    queryFn: () => settingsApi.get(),
    staleTime: 60_000,
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SettingsUpdate) => settingsApi.update(payload),
    onSuccess: (data) => {
      qc.setQueryData(settingsKeys.current, data);
      toast.success("Settings saved");
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Could not save settings";
      toast.error(msg);
    },
  });
}

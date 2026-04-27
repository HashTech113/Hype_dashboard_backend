import { api } from "@/lib/api/client";
import type { Settings, SettingsUpdate } from "@/lib/types/settings";

export const settingsApi = {
  get: () => api.get<Settings>("/settings"),
  update: (payload: SettingsUpdate) =>
    api.patch<Settings>("/settings", payload),
};

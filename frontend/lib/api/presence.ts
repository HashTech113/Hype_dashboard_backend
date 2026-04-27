import { api } from "@/lib/api/client";
import type { PresenceEntry } from "@/lib/types/presence";

export const presenceApi = {
  list: () => api.get<PresenceEntry[]>("/admin/presence"),
};

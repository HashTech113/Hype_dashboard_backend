import { api } from "@/lib/api/client";
import type {
  DashboardResponse,
  HourBucket,
  TimelineItem,
} from "@/lib/types/dashboard";

export const dashboardApi = {
  snapshot: () => api.get<DashboardResponse>("/admin/dashboard"),
  timeline: (limit = 50, offset = 0) =>
    api.get<TimelineItem[]>("/admin/dashboard/timeline", {
      params: { limit, offset },
    }),
  eventsByHour: (hours = 24) =>
    api.get<HourBucket[]>("/admin/dashboard/events-by-hour", {
      params: { hours },
    }),
};

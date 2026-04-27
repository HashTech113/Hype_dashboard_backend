import { api } from "@/lib/api/client";
import type {
  AttendanceEventDetail,
  EventListParams,
  EventType,
} from "@/lib/types/attendance";
import type { Page } from "@/lib/types/common";

export interface ManualEventCreate {
  employee_id: number;
  event_type: EventType;
  event_time: string; // ISO
  camera_id?: number | null;
  note?: string | null;
}

export interface EventUpdatePayload {
  event_type?: EventType;
  event_time?: string; // ISO
  camera_id?: number | null;
  note?: string | null;
}

export interface RecomputeResponse {
  touched: number;
  work_date?: string;
  start_date?: string;
  end_date?: string;
}

export interface CloseDayResponse {
  work_date: string;
  closed: number;
  already_closed: number;
  no_activity: number;
}

export const attendanceApi = {
  listDetailed: (params: EventListParams = {}) =>
    api.get<Page<AttendanceEventDetail>>("/attendance/events/detailed", {
      params: {
        employee_id: params.employee_id,
        camera_id: params.camera_id,
        event_type: params.event_type,
        start: params.start,
        end: params.end,
        is_manual: params.is_manual,
        has_snapshot: params.has_snapshot,
        limit: params.limit,
        offset: params.offset,
      },
    }),

  snapshotBlob: (eventId: number) =>
    api.get<Blob>(`/snapshots/by-event/${eventId}`, { responseType: "blob" }),

  createEvent: (payload: ManualEventCreate) =>
    api.post<AttendanceEventDetail>("/attendance/events", payload),

  updateEvent: (eventId: number, payload: EventUpdatePayload) =>
    api.patch<AttendanceEventDetail>(`/attendance/events/${eventId}`, payload),

  deleteEvent: (eventId: number) =>
    api.delete<void>(`/attendance/events/${eventId}`),

  recomputeDay: (workDate: string, employeeId?: number) =>
    api.post<RecomputeResponse>(
      "/attendance/recompute",
      undefined,
      { params: { work_date: workDate, employee_id: employeeId } },
    ),

  recomputeRange: (startDate: string, endDate: string, employeeId?: number) =>
    api.post<RecomputeResponse>(
      "/attendance/recompute-range",
      undefined,
      {
        params: {
          start_date: startDate,
          end_date: endDate,
          employee_id: employeeId,
        },
      },
    ),

  closeDay: (workDate: string) =>
    api.post<CloseDayResponse>(
      "/attendance/close-day",
      undefined,
      { params: { work_date: workDate } },
    ),
};

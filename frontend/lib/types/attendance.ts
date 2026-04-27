import type { EventType } from "@/lib/types/dashboard";

export type { EventType };

export interface AttendanceEventDetail {
  id: number;
  employee_id: number;
  employee_code: string;
  employee_name: string;
  camera_id: number | null;
  camera_name: string | null;
  event_type: EventType;
  event_time: string;
  confidence: number | null;
  snapshot_available: boolean;
  is_manual: boolean;
  corrected_by: number | null;
  note: string | null;
  created_at: string;
}

export interface EventListParams {
  employee_id?: number;
  camera_id?: number;
  event_type?: EventType;
  start?: string;
  end?: string;
  is_manual?: boolean;
  has_snapshot?: boolean;
  limit?: number;
  offset?: number;
}

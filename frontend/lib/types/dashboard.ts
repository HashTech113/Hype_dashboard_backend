export type EventType = "IN" | "BREAK_OUT" | "BREAK_IN" | "OUT";

export interface DashboardResponse {
  as_of: string;
  work_date: string;
  total_employees: number;
  active_employees: number;
  present_today: number;
  absent_today: number;
  incomplete_today: number;
  inside_office: number;
  on_break: number;
  outside_office: number;
  late_today: number;
  early_exit_today: number;
  events_last_24h: number;
  total_cameras: number;
  active_cameras: number;
}

export interface HourBucket {
  bucket_start: string;
  count: number;
}

export interface TimelineItem {
  event_id: number;
  employee_id: number;
  employee_code: string;
  employee_name: string;
  event_type: EventType;
  event_time: string;
  camera_id: number | null;
  camera_name: string | null;
  confidence: number | null;
  is_manual: boolean;
  snapshot_available: boolean;
}

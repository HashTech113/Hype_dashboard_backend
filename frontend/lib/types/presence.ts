import type { EventType } from "@/lib/types/dashboard";

export type PresenceStatus = "INSIDE" | "ON_BREAK" | "OUTSIDE" | "ABSENT";

export interface PresenceEntry {
  employee_id: number;
  employee_code: string;
  employee_name: string;
  department: string | null;
  status: PresenceStatus;
  last_event_type: EventType | null;
  last_event_time: string | null;
  last_camera_name: string | null;
  last_event_id: number | null;
}

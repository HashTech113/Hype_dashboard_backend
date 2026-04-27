export type UnknownClusterStatus =
  | "PENDING"
  | "PROMOTED"
  | "IGNORED"
  | "MERGED";

export type UnknownCaptureStatus = "KEEP" | "DISCARDED";

export interface UnknownCapture {
  id: number;
  cluster_id: number;
  file_path: string;
  camera_id: number | null;
  camera_name: string | null;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  det_score: number;
  sharpness_score: number;
  captured_at: string;
  status: UnknownCaptureStatus;
  created_at: string;
}

export interface UnknownCluster {
  id: number;
  label: string | null;
  status: UnknownClusterStatus;
  member_count: number;
  first_seen_at: string;
  last_seen_at: string;
  promoted_employee_id: number | null;
  merged_into_cluster_id: number | null;
  representative_capture_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface UnknownClusterDetail extends UnknownCluster {
  captures: UnknownCapture[];
}

export interface UnknownClusterListParams {
  status?: UnknownClusterStatus;
  label?: string;
  limit?: number;
  offset?: number;
}

export interface PromoteToNewPayload {
  employee_code: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  designation?: string | null;
  department?: string | null;
  join_date?: string | null;
  is_active?: boolean;
}

export interface PromoteResponse {
  cluster_id: number;
  employee_id: number;
  employee_code: string;
  employee_name: string;
  cluster_was_new_employee: boolean;
  captures_promoted: number;
  captures_skipped: number;
  total_employee_embeddings: number;
}

export interface ReclusterResponse {
  ran: boolean;
  reason: string;
  captures_total: number;
  clusters_before: number;
  clusters_after_pending: number;
  clusters_merged: number;
  captures_migrated: number;
  noise_count: number;
  duration_ms: number;
}

export interface PurgeResponse {
  cutoff: string;
  clusters_examined: number;
  clusters_deleted: number;
  captures_deleted: number;
  files_deleted: number;
  bytes_freed: number;
}

export interface Settings {
  id: number;
  // Recognition
  face_match_threshold: number;
  face_min_quality: number;
  // Camera pipeline
  cooldown_seconds: number;
  camera_fps: number;
  // Training
  train_min_images: number;
  train_max_images: number;
  auto_update_enabled: boolean;
  auto_update_threshold: number;
  auto_update_cooldown_seconds: number;
  // Office hours + thresholds
  work_start_time: string | null;
  work_end_time: string | null;
  grace_minutes: number;
  early_exit_grace_minutes: number;
  // Meta
  updated_by: number | null;
  updated_at: string;
}

export type SettingsUpdate = Partial<
  Omit<Settings, "id" | "updated_by" | "updated_at">
>;

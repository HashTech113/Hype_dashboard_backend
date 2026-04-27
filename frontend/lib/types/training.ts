export interface FaceImage {
  id: number;
  employee_id: number;
  file_path: string;
  file_hash: string | null;
  width: number | null;
  height: number | null;
  uploaded_by: number | null;
  created_at: string;
}

export interface FaceEmbedding {
  id: number;
  employee_id: number;
  image_id: number;
  dim: number;
  model_name: string;
  quality_score: number;
  created_at: string;
}

export interface TrainingResult {
  employee_id: number;
  accepted: number;
  rejected: number;
  total_embeddings: number;
  errors: string[];
}

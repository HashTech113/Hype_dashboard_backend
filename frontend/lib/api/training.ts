import { api } from "@/lib/api/client";
import type {
  FaceEmbedding,
  FaceImage,
  TrainingResult,
} from "@/lib/types/training";

export const trainingApi = {
  listImages: (employeeId: number) =>
    api.get<FaceImage[]>(`/employees/${employeeId}/training/images`),
  listEmbeddings: (employeeId: number) =>
    api.get<FaceEmbedding[]>(`/employees/${employeeId}/training/embeddings`),
  upload: (employeeId: number, files: File[], replace: boolean) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    return api.post<TrainingResult>(
      `/employees/${employeeId}/training/images`,
      fd,
      { params: { replace } },
    );
  },
  capture: (employeeId: number, cameraId: number) =>
    api.post<TrainingResult>(
      `/employees/${employeeId}/training/capture`,
      undefined,
      { params: { camera_id: cameraId } },
    ),
  deleteImage: (employeeId: number, imageId: number) =>
    api.delete<void>(
      `/employees/${employeeId}/training/images/${imageId}`,
    ),
  rebuildCache: (employeeId: number) =>
    api.post<void>(`/employees/${employeeId}/training/rebuild-cache`),
};

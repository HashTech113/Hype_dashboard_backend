"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { trainingApi } from "@/lib/api/training";

export const trainingKeys = {
  images: (employeeId: number) =>
    ["training", "images", employeeId] as const,
  embeddings: (employeeId: number) =>
    ["training", "embeddings", employeeId] as const,
};

function toastError(err: unknown, fallback: string) {
  const msg = err instanceof ApiError ? err.message : fallback;
  toast.error(msg);
}

export function useFaceImages(employeeId: number | null) {
  return useQuery({
    queryKey:
      employeeId !== null
        ? trainingKeys.images(employeeId)
        : ["training", "images", "none"],
    queryFn: () => trainingApi.listImages(employeeId as number),
    enabled: employeeId !== null,
  });
}

export function useFaceEmbeddings(employeeId: number | null) {
  return useQuery({
    queryKey:
      employeeId !== null
        ? trainingKeys.embeddings(employeeId)
        : ["training", "embeddings", "none"],
    queryFn: () => trainingApi.listEmbeddings(employeeId as number),
    enabled: employeeId !== null,
  });
}

function invalidateTraining(qc: ReturnType<typeof useQueryClient>, employeeId: number) {
  qc.invalidateQueries({ queryKey: trainingKeys.images(employeeId) });
  qc.invalidateQueries({ queryKey: trainingKeys.embeddings(employeeId) });
}

export function useUploadImages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      files,
      replace,
    }: {
      employeeId: number;
      files: File[];
      replace: boolean;
    }) => trainingApi.upload(employeeId, files, replace),
    onSuccess: (result, vars) => {
      invalidateTraining(qc, vars.employeeId);
      if (result.accepted > 0) {
        toast.success(
          `${result.accepted} image${result.accepted === 1 ? "" : "s"} enrolled`,
        );
      }
      if (result.rejected > 0) {
        toast.warning(
          `${result.rejected} image${result.rejected === 1 ? "" : "s"} rejected`,
        );
      }
    },
    onError: (err) => toastError(err, "Upload failed"),
  });
}

export function useCaptureFromCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      cameraId,
    }: {
      employeeId: number;
      cameraId: number;
    }) => trainingApi.capture(employeeId, cameraId),
    onSuccess: (result, vars) => {
      invalidateTraining(qc, vars.employeeId);
      toast.success("Captured face from camera");
    },
    onError: (err) => toastError(err, "Live capture failed"),
  });
}

export function useDeleteFaceImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      imageId,
    }: {
      employeeId: number;
      imageId: number;
    }) => trainingApi.deleteImage(employeeId, imageId),
    onSuccess: (_r, vars) => {
      invalidateTraining(qc, vars.employeeId);
      toast.success("Image removed");
    },
    onError: (err) => toastError(err, "Could not remove image"),
  });
}

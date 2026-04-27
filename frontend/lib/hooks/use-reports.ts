"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { reportsApi } from "@/lib/api/reports";

function toastError(err: unknown) {
  const msg = err instanceof ApiError ? err.message : "Download failed";
  toast.error(msg);
}

function onSuccess() {
  toast.success("Report downloaded");
}

export function useDailyReport() {
  return useMutation({
    mutationFn: ({ workDate }: { workDate: string }) =>
      reportsApi.daily(workDate),
    onSuccess,
    onError: toastError,
  });
}

export function useMonthlyReport() {
  return useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) =>
      reportsApi.monthly(year, month),
    onSuccess,
    onError: toastError,
  });
}

export function useDateRangeReport() {
  return useMutation({
    mutationFn: ({
      startDate,
      endDate,
    }: {
      startDate: string;
      endDate: string;
    }) => reportsApi.dateRange(startDate, endDate),
    onSuccess,
    onError: toastError,
  });
}

export function useEmployeeReport() {
  return useMutation({
    mutationFn: ({
      employeeId,
      startDate,
      endDate,
    }: {
      employeeId: number;
      startDate: string;
      endDate: string;
    }) => reportsApi.employee(employeeId, startDate, endDate),
    onSuccess,
    onError: toastError,
  });
}

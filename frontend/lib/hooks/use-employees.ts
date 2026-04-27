"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { employeesApi } from "@/lib/api/employees";
import type {
  EmployeeCreate,
  EmployeeListParams,
  EmployeeUpdate,
} from "@/lib/types/employee";

export const employeeKeys = {
  all: ["employees"] as const,
  list: (params: EmployeeListParams) =>
    ["employees", "list", params] as const,
  detail: (id: number) => ["employees", "detail", id] as const,
};

export function useEmployeeList(params: EmployeeListParams) {
  return useQuery({
    queryKey: employeeKeys.list(params),
    queryFn: () => employeesApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useEmployee(id: number | null) {
  return useQuery({
    queryKey: id ? employeeKeys.detail(id) : ["employees", "detail", "none"],
    queryFn: () => employeesApi.get(id as number),
    enabled: id !== null,
  });
}

function toastError(err: unknown, fallback: string) {
  const msg = err instanceof ApiError ? err.message : fallback;
  toast.error(msg);
}

export function useCreateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EmployeeCreate) => employeesApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeeKeys.all });
      toast.success("Employee created");
    },
    onError: (err) => toastError(err, "Could not create employee"),
  });
}

export function useUpdateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: EmployeeUpdate }) =>
      employeesApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeeKeys.all });
      toast.success("Employee updated");
    },
    onError: (err) => toastError(err, "Could not update employee"),
  });
}

export function useDeactivateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => employeesApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeeKeys.all });
      toast.success("Employee deactivated");
    },
    onError: (err) => toastError(err, "Could not deactivate employee"),
  });
}

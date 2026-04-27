import { api } from "@/lib/api/client";
import type { Page } from "@/lib/types/common";
import type {
  Employee,
  EmployeeCreate,
  EmployeeListParams,
  EmployeeUpdate,
} from "@/lib/types/employee";

export const employeesApi = {
  list: (params: EmployeeListParams = {}) =>
    api.get<Page<Employee>>("/employees", {
      params: {
        q: params.q,
        is_active: params.is_active,
        department: params.department,
        limit: params.limit,
        offset: params.offset,
      },
    }),
  get: (id: number) => api.get<Employee>(`/employees/${id}`),
  create: (payload: EmployeeCreate) => api.post<Employee>("/employees", payload),
  update: (id: number, payload: EmployeeUpdate) =>
    api.patch<Employee>(`/employees/${id}`, payload),
  remove: (id: number) => api.delete<void>(`/employees/${id}`),
};

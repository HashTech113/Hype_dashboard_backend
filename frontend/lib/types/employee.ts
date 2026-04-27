export interface Employee {
  id: number;
  employee_code: string;
  name: string;
  email: string | null;
  phone: string | null;
  designation: string | null;
  department: string | null;
  join_date: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmployeeCreate {
  employee_code: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  designation?: string | null;
  department?: string | null;
  join_date?: string | null;
  is_active?: boolean;
}

export interface EmployeeUpdate {
  name?: string;
  email?: string | null;
  phone?: string | null;
  designation?: string | null;
  department?: string | null;
  join_date?: string | null;
  is_active?: boolean;
}

export interface EmployeeListParams {
  q?: string;
  is_active?: boolean;
  department?: string;
  limit?: number;
  offset?: number;
}

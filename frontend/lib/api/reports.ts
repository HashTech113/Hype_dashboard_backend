import { api } from "@/lib/api/client";

async function downloadBlob(
  path: string,
  params: Record<string, string | number | boolean | undefined>,
  filename: string,
): Promise<void> {
  const blob = await api.get<Blob>(path, { params, responseType: "blob" });
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    // Let the browser start the download before revoking
    setTimeout(() => URL.revokeObjectURL(url), 2_000);
  }
}

function mm(v: number): string {
  return String(v).padStart(2, "0");
}

export const reportsApi = {
  daily: (workDate: string) =>
    downloadBlob(
      "/reports/daily.xlsx",
      { work_date: workDate },
      `attendance_daily_${workDate}.xlsx`,
    ),

  monthly: (year: number, month: number) =>
    downloadBlob(
      "/reports/monthly.xlsx",
      { year, month },
      `attendance_monthly_${year}-${mm(month)}.xlsx`,
    ),

  dateRange: (startDate: string, endDate: string) =>
    downloadBlob(
      "/reports/date-range.xlsx",
      { start_date: startDate, end_date: endDate },
      `attendance_range_${startDate}_${endDate}.xlsx`,
    ),

  employee: (employeeId: number, startDate: string, endDate: string) =>
    downloadBlob(
      `/reports/employee/${employeeId}.xlsx`,
      { start_date: startDate, end_date: endDate },
      `attendance_employee_${employeeId}_${startDate}_${endDate}.xlsx`,
    ),
};

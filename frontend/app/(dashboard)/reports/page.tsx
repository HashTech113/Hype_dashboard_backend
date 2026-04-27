"use client";

import { DailyReportCard } from "@/components/reports/daily-report-card";
import { DateRangeReportCard } from "@/components/reports/date-range-report-card";
import { EmployeeReportCard } from "@/components/reports/employee-report-card";
import { MonthlyReportCard } from "@/components/reports/monthly-report-card";
import { PageHeader } from "@/components/shared/page-header";

export default function ReportsPage() {
  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6">
      <PageHeader
        title="Reports"
        description="Export attendance data as Excel workbooks. All exports respect the selected timezone and include manual-correction flags."
      />

      <div className="grid gap-4 md:grid-cols-2">
        <DailyReportCard />
        <MonthlyReportCard />
        <DateRangeReportCard />
        <EmployeeReportCard />
      </div>
    </div>
  );
}

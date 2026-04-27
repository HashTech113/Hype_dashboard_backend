"use client";

import { format, subDays } from "date-fns";
import { Download, Loader2, UserSquare2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ReportCardShell } from "@/components/reports/report-card-shell";
import { EmployeePicker } from "@/components/training/employee-picker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useEmployeeReport } from "@/lib/hooks/use-reports";
import type { Employee } from "@/lib/types/employee";

export function EmployeeReportCard() {
  const today = format(new Date(), "yyyy-MM-dd");
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [startDate, setStartDate] = useState<string>(
    format(subDays(new Date(), 30), "yyyy-MM-dd"),
  );
  const [endDate, setEndDate] = useState<string>(today);
  const mut = useEmployeeReport();

  const invalid = !employee || !startDate || !endDate || endDate < startDate;

  function submit() {
    if (!employee) {
      toast.error("Pick an employee first");
      return;
    }
    if (endDate < startDate) {
      toast.error("End date must be on or after start date");
      return;
    }
    mut.mutate({ employeeId: employee.id, startDate, endDate });
  }

  return (
    <ReportCardShell
      title="Per-employee"
      description="One employee, any span — one row per day with ABSENT filled for gaps."
      icon={UserSquare2}
      tone="default"
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Employee</Label>
          <EmployeePicker value={employee} onChange={setEmployee} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="emp-start">Start</Label>
            <Input
              id="emp-start"
              type="date"
              value={startDate}
              max={endDate || today}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="emp-end">End</Label>
            <Input
              id="emp-end"
              type="date"
              value={endDate}
              min={startDate}
              max={today}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
        </div>
        <Button
          onClick={submit}
          disabled={invalid || mut.isPending}
          className="w-full"
        >
          {mut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          {mut.isPending ? "Generating…" : "Download employee report"}
        </Button>
      </div>
    </ReportCardShell>
  );
}

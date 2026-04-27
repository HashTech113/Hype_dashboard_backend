"use client";

import { format, subDays } from "date-fns";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ReportCardShell } from "@/components/reports/report-card-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDateRangeReport } from "@/lib/hooks/use-reports";

export function DateRangeReportCard() {
  const today = format(new Date(), "yyyy-MM-dd");
  const [startDate, setStartDate] = useState<string>(
    format(subDays(new Date(), 7), "yyyy-MM-dd"),
  );
  const [endDate, setEndDate] = useState<string>(today);
  const mut = useDateRangeReport();

  const invalid = !startDate || !endDate || endDate < startDate;

  function submit() {
    if (invalid) {
      toast.error("End date must be on or after start date");
      return;
    }
    mut.mutate({ startDate, endDate });
  }

  return (
    <ReportCardShell
      title="Date range"
      description="All employees, any span up to 366 days — aggregated per employee."
      icon={FileSpreadsheet}
      tone="warning"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="range-start">Start</Label>
            <Input
              id="range-start"
              type="date"
              value={startDate}
              max={endDate || today}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="range-end">End</Label>
            <Input
              id="range-end"
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
          {mut.isPending ? "Generating…" : "Download date-range report"}
        </Button>
      </div>
    </ReportCardShell>
  );
}

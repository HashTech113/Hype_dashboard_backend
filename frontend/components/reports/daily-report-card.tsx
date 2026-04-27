"use client";

import { format } from "date-fns";
import { CalendarDays, Download, Loader2 } from "lucide-react";
import { useState } from "react";

import { ReportCardShell } from "@/components/reports/report-card-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDailyReport } from "@/lib/hooks/use-reports";

export function DailyReportCard() {
  const [workDate, setWorkDate] = useState<string>(
    format(new Date(), "yyyy-MM-dd"),
  );
  const mut = useDailyReport();
  const canSubmit = workDate.length === 10 && !mut.isPending;

  return (
    <ReportCardShell
      title="Daily"
      description="All employees, one calendar day."
      icon={CalendarDays}
      tone="primary"
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="daily-date">Work date</Label>
          <Input
            id="daily-date"
            type="date"
            value={workDate}
            onChange={(e) => setWorkDate(e.target.value)}
            max={format(new Date(), "yyyy-MM-dd")}
          />
        </div>
        <Button
          onClick={() => mut.mutate({ workDate })}
          disabled={!canSubmit}
          className="w-full"
        >
          {mut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          {mut.isPending ? "Generating…" : "Download daily report"}
        </Button>
      </div>
    </ReportCardShell>
  );
}

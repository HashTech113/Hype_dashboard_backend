"use client";

import { format, subDays } from "date-fns";
import { Info, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmployeePicker } from "@/components/training/employee-picker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  useRecomputeDay,
  useRecomputeRange,
} from "@/lib/hooks/use-attendance";
import type { Employee } from "@/lib/types/employee";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RecomputeDialog({ open, onOpenChange }: Props) {
  const today = format(new Date(), "yyyy-MM-dd");
  const [tab, setTab] = useState<"day" | "range">("day");
  const [workDate, setWorkDate] = useState(today);
  const [startDate, setStartDate] = useState(
    format(subDays(new Date(), 7), "yyyy-MM-dd"),
  );
  const [endDate, setEndDate] = useState(today);
  const [employee, setEmployee] = useState<Employee | null>(null);

  const dayMut = useRecomputeDay();
  const rangeMut = useRecomputeRange();
  const submitting = dayMut.isPending || rangeMut.isPending;

  function submit() {
    if (tab === "day") {
      if (!workDate) return toast.error("Pick a date");
      dayMut.mutate(
        { workDate, employeeId: employee?.id },
        { onSuccess: () => onOpenChange(false) },
      );
    } else {
      if (!startDate || !endDate) return toast.error("Pick both dates");
      if (endDate < startDate)
        return toast.error("End date must be on or after start");
      rangeMut.mutate(
        { startDate, endDate, employeeId: employee?.id },
        { onSuccess: () => onOpenChange(false) },
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4" /> Recompute attendance
          </DialogTitle>
          <DialogDescription>
            Rebuilds the daily rollup rows (work time, break time, late/early)
            from the event log.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-start gap-2 rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>
            Safe operation. <strong>No events are modified</strong> — only the
            summary rows are rewritten. Useful after data imports, bulk
            corrections, or changing office-hours settings retroactively.
          </p>
        </div>

        <Tabs value={tab} onValueChange={(v) => setTab(v as "day" | "range")}>
          <TabsList>
            <TabsTrigger value="day">Single day</TabsTrigger>
            <TabsTrigger value="range">Date range</TabsTrigger>
          </TabsList>

          <TabsContent value="day" className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="rc-date">Work date</Label>
              <Input
                id="rc-date"
                type="date"
                value={workDate}
                onChange={(e) => setWorkDate(e.target.value)}
                max={today}
              />
            </div>
          </TabsContent>

          <TabsContent value="range" className="space-y-4 pt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="rc-start">Start</Label>
                <Input
                  id="rc-start"
                  type="date"
                  value={startDate}
                  max={endDate || today}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rc-end">End</Label>
                <Input
                  id="rc-end"
                  type="date"
                  value={endDate}
                  min={startDate}
                  max={today}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <div className="space-y-1.5">
          <Label>Scope</Label>
          <EmployeePicker value={employee} onChange={setEmployee} />
          <p className="text-xs text-muted-foreground">
            Leave empty to recompute every employee who had events in that
            period.
          </p>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Recompute
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

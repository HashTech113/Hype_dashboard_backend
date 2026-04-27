"use client";

import { format } from "date-fns";
import { AlertTriangle, DoorClosed, Loader2 } from "lucide-react";
import { useState } from "react";

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
import { useCloseDay } from "@/lib/hooks/use-attendance";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CloseDayDialog({ open, onOpenChange }: Props) {
  const today = format(new Date(), "yyyy-MM-dd");
  const [workDate, setWorkDate] = useState(today);
  const mut = useCloseDay();

  function submit() {
    if (!workDate) return;
    mut.mutate(workDate, { onSuccess: () => onOpenChange(false) });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <DoorClosed className="h-4 w-4" /> Close day
          </DialogTitle>
          <DialogDescription>
            Finalizes attendance for the selected date. For every employee
            whose last event was a trailing <strong>BREAK_OUT</strong>, it is
            converted to <strong>OUT</strong> in place and flagged as manual.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3 text-xs">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
          <p className="text-warning">
            This <strong>modifies the event log</strong>. Each converted event
            records a note and the admin id. You can reopen the day later, but
            the converted events remain and must be edited/deleted individually.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="cd-date">Work date</Label>
          <Input
            id="cd-date"
            type="date"
            value={workDate}
            max={today}
            onChange={(e) => setWorkDate(e.target.value)}
          />
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mut.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={submit}
            disabled={!workDate || mut.isPending}
          >
            {mut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Close day
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

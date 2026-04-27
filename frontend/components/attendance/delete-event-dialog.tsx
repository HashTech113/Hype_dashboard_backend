"use client";

import { format, parseISO } from "date-fns";
import { Loader2 } from "lucide-react";

import { EventTypeBadge } from "@/components/attendance/event-type-badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeleteEvent } from "@/lib/hooks/use-attendance";
import type { AttendanceEventDetail } from "@/lib/types/attendance";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  event: AttendanceEventDetail | null;
}

export function DeleteEventDialog({ open, onOpenChange, event }: Props) {
  const mut = useDeleteEvent();

  const when = event
    ? (() => {
        try {
          return format(parseISO(event.event_time), "PPpp");
        } catch {
          return event.event_time;
        }
      })()
    : "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this event?</DialogTitle>
          <DialogDescription>
            This permanently removes the event from the log. The day&apos;s
            rollup (work time, break time, late/early flags) will be
            recomputed immediately.
          </DialogDescription>
        </DialogHeader>

        {event && (
          <div className="rounded-md border bg-muted/20 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <EventTypeBadge type={event.event_type} />
              <span className="font-medium">{event.employee_name}</span>
              <span className="text-muted-foreground">
                · {event.employee_code}
              </span>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              {when}
              {event.camera_name ? ` · ${event.camera_name}` : ""}
            </p>
            {event.note && (
              <p className="mt-2 text-xs italic text-muted-foreground">
                &ldquo;{event.note}&rdquo;
              </p>
            )}
          </div>
        )}

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
            disabled={mut.isPending || !event}
            onClick={() =>
              event &&
              mut.mutate(event.id, {
                onSuccess: () => onOpenChange(false),
              })
            }
          >
            {mut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Delete event
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

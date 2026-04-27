"use client";

import { format, parseISO } from "date-fns";

import { EventTypeBadge } from "@/components/attendance/event-type-badge";
import { AuthImage } from "@/components/shared/auth-image";
import type { AttendanceEventDetail } from "@/lib/types/attendance";

interface Props {
  event: AttendanceEventDetail;
  onClick: () => void;
  showEmployee?: boolean;
}

export function SnapshotCard({ event, onClick, showEmployee = true }: Props) {
  const time = (() => {
    try {
      return format(parseISO(event.event_time), "HH:mm:ss");
    } catch {
      return "—";
    }
  })();

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative flex flex-col overflow-hidden rounded-lg border bg-card text-left transition-all hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <AuthImage
        eventId={event.id}
        className="aspect-square w-full"
        alt={`${event.employee_name} · ${event.event_type}`}
      />
      <div className="absolute left-2 top-2">
        <EventTypeBadge type={event.event_type} />
      </div>
      <div className="flex min-w-0 flex-col gap-0.5 border-t bg-background/95 p-2.5">
        {showEmployee && (
          <p className="truncate text-sm font-medium">{event.employee_name}</p>
        )}
        <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
          <span className="tabular-nums">{time}</span>
          {event.confidence !== null && (
            <span className="tabular-nums">
              {(event.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

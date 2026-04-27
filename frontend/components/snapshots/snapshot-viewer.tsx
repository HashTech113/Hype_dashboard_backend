"use client";

import { format, parseISO } from "date-fns";
import {
  AlertCircle,
  Camera as CameraIcon,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
} from "lucide-react";
import { useCallback, useEffect } from "react";

import { EventTypeBadge } from "@/components/attendance/event-type-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSnapshotUrl } from "@/lib/hooks/use-attendance";
import type { AttendanceEventDetail } from "@/lib/types/attendance";

interface Props {
  events: AttendanceEventDetail[];
  index: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onIndexChange: (index: number) => void;
}

export function SnapshotViewer({
  events,
  index,
  open,
  onOpenChange,
  onIndexChange,
}: Props) {
  const current = events[index] ?? null;
  const { url, loading, error } = useSnapshotUrl(
    current?.snapshot_available ? current.id : null,
  );

  const hasPrev = index > 0;
  const hasNext = index < events.length - 1;

  const go = useCallback(
    (delta: number) => {
      const next = index + delta;
      if (next >= 0 && next < events.length) onIndexChange(next);
    },
    [index, events.length, onIndexChange],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        go(-1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        go(1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, go]);

  async function download() {
    if (!url || !current) return;
    const a = document.createElement("a");
    a.href = url;
    const ts = format(parseISO(current.event_time), "yyyyMMdd-HHmmss");
    a.download = `snap_${current.employee_code}_${ts}_${current.event_type}.jpg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {current?.employee_name || "—"}
            {current && <EventTypeBadge type={current.event_type} />}
            {current?.is_manual && <Badge variant="secondary">manual</Badge>}
          </DialogTitle>
          <DialogDescription asChild>
            <div className="inline-flex flex-wrap items-center gap-2 text-xs">
              {current && (
                <>
                  <span>{format(parseISO(current.event_time), "PPpp")}</span>
                  {current.camera_name && (
                    <span className="inline-flex items-center gap-1">
                      <CameraIcon className="h-3 w-3" />
                      {current.camera_name}
                    </span>
                  )}
                  {current.confidence !== null && (
                    <span className="tabular-nums">
                      conf {(current.confidence * 100).toFixed(1)}%
                    </span>
                  )}
                  {events.length > 1 && (
                    <span className="ml-auto text-muted-foreground">
                      {index + 1} / {events.length}
                    </span>
                  )}
                </>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>

        <div className="relative overflow-hidden rounded-md border bg-black/90">
          {!current?.snapshot_available ? (
            <Empty message="This event has no snapshot." />
          ) : loading ? (
            <div className="flex aspect-video items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading snapshot…
            </div>
          ) : error || !url ? (
            <Empty message={error ?? "Snapshot unavailable."} isError />
          ) : (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={url}
              alt="Event snapshot"
              className="mx-auto block max-h-[70vh] w-auto object-contain"
            />
          )}

          {events.length > 1 && (
            <>
              <NavButton
                side="left"
                onClick={() => go(-1)}
                disabled={!hasPrev}
                aria="Previous"
              />
              <NavButton
                side="right"
                onClick={() => go(1)}
                disabled={!hasNext}
                aria="Next"
              />
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          {current?.note ? (
            <p className="max-w-md truncate text-xs text-muted-foreground">
              <span className="font-medium">Note:</span> {current.note}
            </p>
          ) : (
            <span />
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={download}
            disabled={!url}
          >
            <Download className="h-4 w-4" />
            Download
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Empty({ message, isError }: { message: string; isError?: boolean }) {
  return (
    <div className="flex aspect-video flex-col items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
      <AlertCircle
        className={isError ? "h-5 w-5 text-destructive" : "h-5 w-5"}
      />
      <p className="text-center">{message}</p>
    </div>
  );
}

function NavButton({
  side,
  onClick,
  disabled,
  aria,
}: {
  side: "left" | "right";
  onClick: () => void;
  disabled: boolean;
  aria: string;
}) {
  return (
    <button
      type="button"
      aria-label={aria}
      onClick={onClick}
      disabled={disabled}
      className={`absolute top-1/2 -translate-y-1/2 rounded-full bg-background/80 p-2 shadow backdrop-blur transition-opacity hover:bg-background disabled:opacity-30 ${
        side === "left" ? "left-3" : "right-3"
      }`}
    >
      {side === "left" ? (
        <ChevronLeft className="h-5 w-5" />
      ) : (
        <ChevronRight className="h-5 w-5" />
      )}
    </button>
  );
}

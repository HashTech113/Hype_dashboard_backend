import { ArrowDownToLine, ArrowUpFromLine, Coffee, LogIn } from "lucide-react";

import { cn } from "@/lib/utils";
import type { EventType } from "@/lib/types/attendance";

const CONFIG: Record<
  EventType,
  { label: string; className: string; Icon: typeof ArrowDownToLine }
> = {
  IN: {
    label: "IN",
    className: "bg-success/15 text-success border-success/30",
    Icon: ArrowDownToLine,
  },
  BREAK_OUT: {
    label: "Break out",
    className: "bg-warning/15 text-warning border-warning/30",
    Icon: Coffee,
  },
  BREAK_IN: {
    label: "Break in",
    className: "bg-primary/10 text-primary border-primary/30",
    Icon: LogIn,
  },
  OUT: {
    label: "OUT",
    className: "bg-muted text-muted-foreground border-border",
    Icon: ArrowUpFromLine,
  },
};

export function EventTypeBadge({
  type,
  className,
}: {
  type: EventType;
  className?: string;
}) {
  const { label, className: toneClass, Icon } = CONFIG[type];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneClass,
        className,
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

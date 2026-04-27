import { Coffee, DoorClosed, DoorOpen, UserX } from "lucide-react";

import { cn } from "@/lib/utils";
import type { PresenceStatus } from "@/lib/types/presence";

const CONFIG: Record<
  PresenceStatus,
  { label: string; className: string; Icon: typeof DoorClosed }
> = {
  INSIDE: {
    label: "Inside",
    className: "bg-success/15 text-success border-success/30",
    Icon: DoorClosed,
  },
  ON_BREAK: {
    label: "On break",
    className: "bg-warning/15 text-warning border-warning/30",
    Icon: Coffee,
  },
  OUTSIDE: {
    label: "Outside",
    className: "bg-primary/10 text-primary border-primary/30",
    Icon: DoorOpen,
  },
  ABSENT: {
    label: "Absent",
    className: "bg-muted text-muted-foreground border-border",
    Icon: UserX,
  },
};

export function StatusBadge({
  status,
  className,
}: {
  status: PresenceStatus;
  className?: string;
}) {
  const { label, className: toneClass, Icon } = CONFIG[status];
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

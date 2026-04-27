"use client";

import { format, isToday, isYesterday, parseISO } from "date-fns";
import { ImageOff } from "lucide-react";
import { useMemo } from "react";

import { SnapshotCard } from "@/components/snapshots/snapshot-card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AttendanceEventDetail } from "@/lib/types/attendance";
import type { GroupMode } from "@/components/snapshots/snapshot-filters";

interface Props {
  events: AttendanceEventDetail[] | undefined;
  loading: boolean;
  group: GroupMode;
  onOpen: (index: number) => void;
}

interface Group {
  key: string;
  heading: string;
  subHeading?: string;
  indices: number[];
  showEmployee: boolean;
}

function dateHeading(iso: string): string {
  try {
    const d = parseISO(iso);
    if (isToday(d)) return "Today";
    if (isYesterday(d)) return "Yesterday";
    return format(d, "EEEE · MMM d, yyyy");
  } catch {
    return iso.slice(0, 10);
  }
}

function buildGroups(
  events: AttendanceEventDetail[],
  mode: GroupMode,
): Group[] {
  if (mode === "none") {
    return [
      {
        key: "all",
        heading: "",
        indices: events.map((_, i) => i),
        showEmployee: true,
      },
    ];
  }
  const map = new Map<string, Group>();
  events.forEach((ev, i) => {
    if (mode === "date") {
      const dateKey = (() => {
        try {
          return format(parseISO(ev.event_time), "yyyy-MM-dd");
        } catch {
          return ev.event_time.slice(0, 10);
        }
      })();
      const g = map.get(dateKey);
      if (g) {
        g.indices.push(i);
      } else {
        map.set(dateKey, {
          key: dateKey,
          heading: dateHeading(ev.event_time),
          indices: [i],
          showEmployee: true,
        });
      }
    } else {
      // employee
      const empKey = `emp-${ev.employee_id}`;
      const g = map.get(empKey);
      if (g) {
        g.indices.push(i);
      } else {
        map.set(empKey, {
          key: empKey,
          heading: ev.employee_name || ev.employee_code,
          subHeading: ev.employee_code,
          indices: [i],
          showEmployee: false,
        });
      }
    }
  });
  return Array.from(map.values());
}

export function SnapshotGrid({ events, loading, group, onOpen }: Props) {
  const groups = useMemo(
    () => (events ? buildGroups(events, group) : []),
    [events, group],
  );

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="aspect-square rounded-lg" />
        ))}
      </div>
    );
  }

  if (!events || events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-sm text-muted-foreground">
        <ImageOff className="h-5 w-5" />
        No snapshots match these filters.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {groups.map((g) => (
        <section key={g.key}>
          {g.heading && (
            <header className="mb-3 flex items-baseline justify-between gap-3 border-b pb-2">
              <div>
                <h3 className="text-sm font-semibold">{g.heading}</h3>
                {g.subHeading && (
                  <p className="text-xs text-muted-foreground">
                    {g.subHeading}
                  </p>
                )}
              </div>
              <p className="text-xs tabular-nums text-muted-foreground">
                {g.indices.length} snapshot{g.indices.length === 1 ? "" : "s"}
              </p>
            </header>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {g.indices.map((i) => (
              <SnapshotCard
                key={events[i].id}
                event={events[i]}
                onClick={() => onOpen(i)}
                showEmployee={g.showEmployee}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

"use client";

import { format, formatDistanceToNow, parseISO } from "date-fns";
import { Camera, ChevronRight, Clock, Pencil } from "lucide-react";
import Link from "next/link";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTimeline } from "@/lib/hooks/use-dashboard";
import type { EventType, TimelineItem } from "@/lib/types/dashboard";
import { cn } from "@/lib/utils";

const EVENT_VARIANT: Record<EventType, { label: string; className: string }> = {
  IN: { label: "IN", className: "bg-success/15 text-success" },
  BREAK_OUT: { label: "Break out", className: "bg-warning/15 text-warning" },
  BREAK_IN: { label: "Break in", className: "bg-primary/15 text-primary" },
  OUT: { label: "OUT", className: "bg-muted text-muted-foreground" },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

function renderTime(iso: string): { absolute: string; relative: string } {
  try {
    const dt = parseISO(iso);
    return {
      absolute: format(dt, "HH:mm:ss"),
      relative: formatDistanceToNow(dt, { addSuffix: true }),
    };
  } catch {
    return { absolute: iso, relative: "" };
  }
}

function Row({ item }: { item: TimelineItem }) {
  const { absolute, relative } = renderTime(item.event_time);
  const variant = EVENT_VARIANT[item.event_type];
  // Linking to /employees pre-filtered by the person's code so clicking
  // a card jumps you to that person's full record. The Employees page
  // honours `?q=` as a search filter (see employees/page.tsx). If a
  // dedicated /employees/[id] detail route is added later this hook
  // moves there with a 1-line change.
  const detailHref = item.employee_code
    ? `/employees?q=${encodeURIComponent(item.employee_code)}`
    : "/employees";
  return (
    <li>
      <Link
        href={detailHref}
        className="group -mx-2 flex items-center gap-4 rounded-md px-2 py-3 transition-colors hover:bg-muted/50 focus-visible:bg-muted/70 focus-visible:outline-none"
      >
        <Avatar className="h-9 w-9">
          <AvatarFallback className="text-xs">
            {initials(item.employee_name || item.employee_code)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium">
              {item.employee_name || item.employee_code}
            </p>
            <span
              className={cn(
                "inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                variant.className,
              )}
            >
              {variant.label}
            </span>
            {item.is_manual && (
              <Badge variant="secondary" className="gap-1">
                <Pencil className="h-3 w-3" /> manual
              </Badge>
            )}
          </div>
          <p className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {absolute}
              {relative && <span className="opacity-70">· {relative}</span>}
            </span>
            {item.camera_name && (
              <span className="inline-flex items-center gap-1">
                <Camera className="h-3 w-3" />
                {item.camera_name}
              </span>
            )}
            {item.confidence !== null && (
              <span className="tabular-nums">
                conf {(item.confidence * 100).toFixed(1)}%
              </span>
            )}
          </p>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </Link>
    </li>
  );
}

export function TimelineFeed() {
  const { data, isLoading } = useTimeline(25);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Live activity</CardTitle>
          <CardDescription>
            People entering, exiting, on break — click a card for details
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <ul className="divide-y">
            {Array.from({ length: 6 }).map((_, i) => (
              <li key={i} className="flex items-center gap-4 py-3">
                <Skeleton className="h-9 w-9 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3 w-40" />
                  <Skeleton className="h-3 w-64" />
                </div>
              </li>
            ))}
          </ul>
        ) : !data || data.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Clock className="h-5 w-5" />
            <p>No activity yet.</p>
            <p className="text-xs">
              Walk past a camera, or{" "}
              <Link href="/training" className="text-primary underline">
                add a person via Face Training
              </Link>
              .
            </p>
          </div>
        ) : (
          <ul className="divide-y">
            {data.map((item) => (
              <Row key={item.event_id} item={item} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

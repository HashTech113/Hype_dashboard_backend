"use client";

import { format, formatDistanceToNow, parseISO } from "date-fns";
import { Camera, Users } from "lucide-react";

import { StatusBadge } from "@/components/presence/status-badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PresenceEntry } from "@/lib/types/presence";

function initials(name: string, code: string): string {
  const source = (name || code || "").trim();
  const parts = source.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

function fmtLast(iso: string | null): { absolute: string; relative: string } {
  if (!iso) return { absolute: "—", relative: "" };
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

interface Props {
  rows: PresenceEntry[] | undefined;
  loading: boolean;
}

export function PresenceTable({ rows, loading }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[40%]">Employee</TableHead>
          <TableHead>Department</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Last event</TableHead>
          <TableHead>Camera</TableHead>
          <TableHead className="text-right">Time</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <TableRow key={`s-${i}`}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <Skeleton className="h-9 w-9 rounded-full" />
                  <div className="flex flex-col gap-1.5">
                    <Skeleton className="h-3 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-5 w-20 rounded-full" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-20" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-24" />
              </TableCell>
              <TableCell className="text-right">
                <Skeleton className="ml-auto h-3 w-16" />
              </TableCell>
            </TableRow>
          ))
        ) : !rows || rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={6} className="py-12 text-center">
              <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                <Users className="h-5 w-5" />
                No employees match this filter.
              </div>
            </TableCell>
          </TableRow>
        ) : (
          rows.map((r) => {
            const { absolute, relative } = fmtLast(r.last_event_time);
            return (
              <TableRow key={r.employee_id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <Avatar className="h-9 w-9">
                      <AvatarFallback className="text-xs">
                        {initials(r.employee_name, r.employee_code)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0">
                      <p className="truncate font-medium">{r.employee_name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {r.employee_code}
                      </p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {r.department || "—"}
                </TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                </TableCell>
                <TableCell className="text-sm">
                  {r.last_event_type ? (
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {r.last_event_type.replace("_", " ")}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {r.last_camera_name ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Camera className="h-3.5 w-3.5" />
                      {r.last_camera_name}
                    </span>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex flex-col items-end">
                    <span className="text-sm tabular-nums">{absolute}</span>
                    {relative && (
                      <span className="text-[11px] text-muted-foreground">
                        {relative}
                      </span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })
        )}
      </TableBody>
    </Table>
  );
}

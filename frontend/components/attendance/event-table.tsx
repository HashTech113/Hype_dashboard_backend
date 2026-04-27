"use client";

import { format, formatDistanceToNow, parseISO } from "date-fns";
import {
  Camera as CameraIcon,
  Image as ImageIcon,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";

import { EventTypeBadge } from "@/components/attendance/event-type-badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AttendanceEventDetail } from "@/lib/types/attendance";

function initials(name: string, code: string): string {
  const src = (name || code || "").trim();
  const parts = src.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

function fmt(iso: string): { absolute: string; relative: string } {
  try {
    const dt = parseISO(iso);
    return {
      absolute: format(dt, "MMM d · HH:mm:ss"),
      relative: formatDistanceToNow(dt, { addSuffix: true }),
    };
  } catch {
    return { absolute: iso, relative: "" };
  }
}

interface Props {
  rows: AttendanceEventDetail[] | undefined;
  loading: boolean;
  onOpenSnapshot: (event: AttendanceEventDetail) => void;
  onEdit: (event: AttendanceEventDetail) => void;
  onDelete: (event: AttendanceEventDetail) => void;
}

export function EventTable({
  rows,
  loading,
  onOpenSnapshot,
  onEdit,
  onDelete,
}: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[26%]">Employee</TableHead>
          <TableHead>Event</TableHead>
          <TableHead>Timestamp</TableHead>
          <TableHead>Camera</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead className="w-24 text-right">Snapshot</TableHead>
          <TableHead className="w-12" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => (
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
                <Skeleton className="h-5 w-24 rounded-full" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-32" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-12" />
              </TableCell>
              <TableCell className="text-right">
                <Skeleton className="ml-auto h-8 w-20 rounded-md" />
              </TableCell>
              <TableCell />
            </TableRow>
          ))
        ) : !rows || rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={7} className="py-12 text-center">
              <p className="text-sm text-muted-foreground">
                No events match these filters.
              </p>
            </TableCell>
          </TableRow>
        ) : (
          rows.map((e) => {
            const { absolute, relative } = fmt(e.event_time);
            return (
              <TableRow key={e.id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <Avatar className="h-9 w-9">
                      <AvatarFallback className="text-xs">
                        {initials(e.employee_name, e.employee_code)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0">
                      <p className="truncate font-medium">{e.employee_name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {e.employee_code}
                      </p>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <EventTypeBadge type={e.event_type} />
                    {e.is_manual && (
                      <Badge variant="secondary" className="gap-1">
                        <Pencil className="h-3 w-3" /> manual
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col leading-tight">
                    <span className="text-sm tabular-nums">{absolute}</span>
                    {relative && (
                      <span className="text-[11px] text-muted-foreground">
                        {relative}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {e.camera_name ? (
                    <span className="inline-flex items-center gap-1.5">
                      <CameraIcon className="h-3.5 w-3.5" />
                      {e.camera_name}
                    </span>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-sm tabular-nums text-muted-foreground">
                  {e.confidence !== null
                    ? `${(e.confidence * 100).toFixed(1)}%`
                    : "—"}
                </TableCell>
                <TableCell className="text-right">
                  {e.snapshot_available ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5"
                      onClick={() => onOpenSnapshot(e)}
                    >
                      <ImageIcon className="h-3.5 w-3.5" />
                      View
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Row actions"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <DropdownMenuItem onClick={() => onEdit(e)}>
                        <Pencil className="mr-2 h-4 w-4" /> Edit event
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={() => onDelete(e)}
                      >
                        <Trash2 className="mr-2 h-4 w-4" /> Delete event
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            );
          })
        )}
      </TableBody>
    </Table>
  );
}

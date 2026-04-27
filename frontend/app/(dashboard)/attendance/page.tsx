"use client";

import { DoorClosed, Plus, RefreshCw, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import { CloseDayDialog } from "@/components/attendance/close-day-dialog";
import { DeleteEventDialog } from "@/components/attendance/delete-event-dialog";
import {
  EventFilters,
  type EventFiltersState,
} from "@/components/attendance/event-filters";
import { EventTable } from "@/components/attendance/event-table";
import { ManualEventDialog } from "@/components/attendance/manual-event-dialog";
import { RecomputeDialog } from "@/components/attendance/recompute-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { SnapshotViewer } from "@/components/snapshots/snapshot-viewer";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useEventList } from "@/lib/hooks/use-attendance";
import type {
  AttendanceEventDetail,
  EventListParams,
} from "@/lib/types/attendance";

const PAGE_SIZE = 50;

function toIsoStart(date: string): string | undefined {
  if (!date) return undefined;
  return new Date(`${date}T00:00:00`).toISOString();
}
function toIsoEnd(date: string): string | undefined {
  if (!date) return undefined;
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + 1);
  return d.toISOString();
}

export default function AttendancePage() {
  const [filters, setFilters] = useState<EventFiltersState>({
    employee: null,
    dateFrom: "",
    dateTo: "",
    eventType: "ALL",
  });
  const [offset, setOffset] = useState(0);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  const [manualOpen, setManualOpen] = useState(false);
  const [editing, setEditing] = useState<AttendanceEventDetail | null>(null);
  const [deleting, setDeleting] = useState<AttendanceEventDetail | null>(null);
  const [recomputeOpen, setRecomputeOpen] = useState(false);
  const [closeDayOpen, setCloseDayOpen] = useState(false);

  const params: EventListParams = useMemo(
    () => ({
      employee_id: filters.employee?.id,
      event_type: filters.eventType === "ALL" ? undefined : filters.eventType,
      start: toIsoStart(filters.dateFrom),
      end: toIsoEnd(filters.dateTo),
      limit: PAGE_SIZE,
      offset,
    }),
    [filters, offset],
  );

  const { data, isLoading, isFetching } = useEventList(params);
  const events = data?.items ?? [];

  function updateFilters(next: EventFiltersState) {
    setFilters(next);
    setOffset(0);
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <PageHeader
        title="Attendance logs"
        description="Every IN, OUT, and break event across all cameras. Add manual events, correct mistakes, or recompute a day's rollup."
        actions={
          <>
            <Button
              onClick={() => {
                setEditing(null);
                setManualOpen(true);
              }}
            >
              <Plus className="h-4 w-4" /> Add event
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline">
                  <Wrench className="h-4 w-4" /> Tools
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuItem onClick={() => setRecomputeOpen(true)}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Recompute attendance
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setCloseDayOpen(true)}>
                  <DoorClosed className="mr-2 h-4 w-4" />
                  Close day
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      <Card>
        <div className="border-b p-4">
          <EventFilters value={filters} onChange={updateFilters} />
        </div>
        <EventTable
          rows={events}
          loading={isLoading}
          onOpenSnapshot={(ev) => {
            const idx = events.findIndex((x) => x.id === ev.id);
            setViewerIndex(idx >= 0 ? idx : null);
          }}
          onEdit={(ev) => {
            setEditing(ev);
            setManualOpen(true);
          }}
          onDelete={(ev) => setDeleting(ev)}
        />
        <PaginationBar
          total={data?.total ?? 0}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={setOffset}
          loading={isFetching}
        />
      </Card>

      <SnapshotViewer
        events={events}
        index={viewerIndex ?? 0}
        open={viewerIndex !== null}
        onOpenChange={(v) => !v && setViewerIndex(null)}
        onIndexChange={setViewerIndex}
      />

      <ManualEventDialog
        open={manualOpen}
        onOpenChange={(v) => {
          setManualOpen(v);
          if (!v) setEditing(null);
        }}
        mode={editing ? "edit" : "create"}
        event={editing}
        presetEmployee={filters.employee}
      />

      <DeleteEventDialog
        open={!!deleting}
        onOpenChange={(v) => !v && setDeleting(null)}
        event={deleting}
      />

      <RecomputeDialog open={recomputeOpen} onOpenChange={setRecomputeOpen} />
      <CloseDayDialog open={closeDayOpen} onOpenChange={setCloseDayOpen} />
    </div>
  );
}

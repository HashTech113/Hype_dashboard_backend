"use client";

import { useMemo, useState } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { PaginationBar } from "@/components/shared/pagination-bar";
import {
  SnapshotFilters,
  type SnapshotFiltersState,
} from "@/components/snapshots/snapshot-filters";
import { SnapshotGrid } from "@/components/snapshots/snapshot-grid";
import { SnapshotViewer } from "@/components/snapshots/snapshot-viewer";
import { Card } from "@/components/ui/card";
import { useEventList } from "@/lib/hooks/use-attendance";
import type { EventListParams } from "@/lib/types/attendance";

const PAGE_SIZE = 48;

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

export default function SnapshotsPage() {
  const [filters, setFilters] = useState<SnapshotFiltersState>({
    employee: null,
    dateFrom: "",
    dateTo: "",
    eventType: "ALL",
    group: "date",
  });
  const [offset, setOffset] = useState(0);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  const params: EventListParams = useMemo(
    () => ({
      employee_id: filters.employee?.id,
      event_type: filters.eventType === "ALL" ? undefined : filters.eventType,
      start: toIsoStart(filters.dateFrom),
      end: toIsoEnd(filters.dateTo),
      has_snapshot: true,
      limit: PAGE_SIZE,
      offset,
    }),
    [filters, offset],
  );

  const { data, isLoading, isFetching } = useEventList(params);
  const events = data?.items ?? [];

  function updateFilters(next: SnapshotFiltersState) {
    setFilters(next);
    setOffset(0);
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <PageHeader
        title="Snapshots"
        description="Every event capture, organized by date or employee. Click a card to zoom in, download, or navigate with arrow keys."
      />

      <Card className="p-4">
        <SnapshotFilters value={filters} onChange={updateFilters} />
      </Card>

      <SnapshotGrid
        events={events}
        loading={isLoading}
        group={filters.group}
        onOpen={setViewerIndex}
      />

      <Card>
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
    </div>
  );
}

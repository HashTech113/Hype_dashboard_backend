"use client";

/**
 * Dashboard top-tile grid (H11 fix).
 *
 * Each section handles { isLoading, isError, refetch } so when the backend
 * is down or a query fails, the operator sees an actionable error card
 * with a Retry button — instead of zeros that look like a healthy-but-
 * empty system. The previous version destructured only { data, isLoading }
 * and silently rendered placeholders on failure.
 */

import {
  AlarmClock,
  AlertTriangle,
  Camera,
  CircleDot,
  Coffee,
  DoorClosed,
  DoorOpen,
  Hourglass,
  RefreshCw,
  Users,
  UserX,
} from "lucide-react";

import { StatCard } from "@/components/shared/stat-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError } from "@/lib/api/client";
import { useDashboardSnapshot } from "@/lib/hooks/use-dashboard";

function ErrorTile({
  error,
  refetch,
  span = "sm:col-span-2 xl:col-span-4",
}: {
  error: unknown;
  refetch: () => void;
  span?: string;
}) {
  const msg =
    error instanceof ApiError
      ? error.message
      : "Could not load dashboard stats.";
  return (
    <Card
      className={`${span} flex items-start gap-3 border-destructive/30 bg-destructive/5 p-4`}
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
      <div className="flex-1">
        <p className="text-sm font-semibold">Stats unavailable</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{msg}</p>
      </div>
      <Button size="sm" variant="outline" onClick={refetch}>
        <RefreshCw className="mr-1 h-3.5 w-3.5" />
        Retry
      </Button>
    </Card>
  );
}

export function PrimaryStats() {
  const { data, isLoading, isError, error, refetch } = useDashboardSnapshot();
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {isError ? (
        <ErrorTile error={error} refetch={() => refetch()} />
      ) : (
        <>
          <StatCard
            label="Registered people"
            value={data?.total_employees}
            hint={data ? `${data.active_employees} active` : undefined}
            icon={Users}
            tone="primary"
            loading={isLoading}
          />
          <StatCard
            label="Seen today"
            value={data?.present_today}
            hint={data ? `${data.incomplete_today} still in view` : undefined}
            icon={CircleDot}
            tone="success"
            loading={isLoading}
          />
          <StatCard
            label="Currently in view"
            value={data?.inside_office}
            hint="On camera right now"
            icon={DoorClosed}
            tone="success"
            loading={isLoading}
          />
          <StatCard
            label="Briefly away"
            value={data?.on_break}
            hint="Stepped out, expected back"
            icon={Coffee}
            tone="warning"
            loading={isLoading}
          />
        </>
      )}
    </div>
  );
}

export function SecondaryStats() {
  const { data, isLoading, isError, error, refetch } = useDashboardSnapshot();
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      {isError ? (
        <ErrorTile error={error} refetch={() => refetch()} span="sm:col-span-2 xl:col-span-5" />
      ) : (
        <>
          <StatCard
            label="Not seen today"
            value={data?.absent_today}
            icon={UserX}
            tone="destructive"
            loading={isLoading}
          />
          <StatCard
            label="Departed"
            value={data?.outside_office}
            hint="Last seen leaving"
            icon={DoorOpen}
            loading={isLoading}
          />
          <StatCard
            label="Late entries"
            value={data?.late_today}
            icon={AlarmClock}
            tone="warning"
            loading={isLoading}
          />
          <StatCard
            label="Early exits"
            value={data?.early_exit_today}
            icon={AlertTriangle}
            tone="warning"
            loading={isLoading}
          />
          <StatCard
            label="Cameras"
            value={
              data ? `${data.active_cameras}/${data.total_cameras}` : undefined
            }
            hint="Active / Total"
            icon={Camera}
            tone="primary"
            loading={isLoading}
          />
        </>
      )}
    </div>
  );
}

export function TertiaryStats() {
  const { data, isLoading, isError, error, refetch } = useDashboardSnapshot();
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {isError ? (
        <ErrorTile error={error} refetch={() => refetch()} span="sm:col-span-2 xl:col-span-3" />
      ) : (
        <StatCard
          label="Events · last 24h"
          value={data?.events_last_24h}
          hint="Entries + exits across all cameras"
          icon={Hourglass}
          tone="primary"
          loading={isLoading}
        />
      )}
    </div>
  );
}

export function StatsGrid() {
  return (
    <div className="flex flex-col gap-4">
      <PrimaryStats />
      <SecondaryStats />
    </div>
  );
}

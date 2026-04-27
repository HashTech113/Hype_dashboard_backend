"use client";

import {
  AlarmClock,
  AlertTriangle,
  Camera,
  CircleDot,
  Coffee,
  DoorClosed,
  DoorOpen,
  Hourglass,
  Users,
  UserX,
} from "lucide-react";

import { StatCard } from "@/components/shared/stat-card";
import { useDashboardSnapshot } from "@/lib/hooks/use-dashboard";

export function PrimaryStats() {
  const { data, isLoading } = useDashboardSnapshot();
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Total employees"
        value={data?.total_employees}
        hint={data ? `${data.active_employees} active` : undefined}
        icon={Users}
        tone="primary"
        loading={isLoading}
      />
      <StatCard
        label="Present today"
        value={data?.present_today}
        hint={
          data ? `${data.incomplete_today} still in office` : undefined
        }
        icon={CircleDot}
        tone="success"
        loading={isLoading}
      />
      <StatCard
        label="Inside office"
        value={data?.inside_office}
        hint="Currently working"
        icon={DoorClosed}
        tone="success"
        loading={isLoading}
      />
      <StatCard
        label="On break"
        value={data?.on_break}
        hint="Temporarily out"
        icon={Coffee}
        tone="warning"
        loading={isLoading}
      />
    </div>
  );
}

export function SecondaryStats() {
  const { data, isLoading } = useDashboardSnapshot();
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <StatCard
        label="Absent"
        value={data?.absent_today}
        icon={UserX}
        tone="destructive"
        loading={isLoading}
      />
      <StatCard
        label="Outside office"
        value={data?.outside_office}
        hint="Clocked out"
        icon={DoorOpen}
        loading={isLoading}
      />
      <StatCard
        label="Late today"
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
    </div>
  );
}

export function TertiaryStats() {
  const { data, isLoading } = useDashboardSnapshot();
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatCard
        label="Events · last 24h"
        value={data?.events_last_24h}
        icon={Hourglass}
        tone="primary"
        loading={isLoading}
      />
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

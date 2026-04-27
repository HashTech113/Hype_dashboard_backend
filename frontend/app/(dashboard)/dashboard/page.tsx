"use client";

import { EventsChart } from "@/components/dashboard/events-chart";
import { PresenceChart } from "@/components/dashboard/presence-chart";
import {
  PrimaryStats,
  SecondaryStats,
} from "@/components/dashboard/stats-grid";
import { TimelineFeed } from "@/components/dashboard/timeline-feed";
import { LiveIndicator } from "@/components/shared/live-indicator";
import { useDashboardSnapshot } from "@/lib/hooks/use-dashboard";

export default function DashboardPage() {
  const { data, isFetching, isError } = useDashboardSnapshot();

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Overview</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Live snapshot of attendance, presence, and recent events.
          </p>
        </div>
        <LiveIndicator
          asOf={data?.as_of ?? null}
          stale={isError || (!isFetching && !data)}
        />
      </header>

      <section aria-label="Primary stats" className="flex flex-col gap-4">
        <PrimaryStats />
        <SecondaryStats />
      </section>

      <section
        aria-label="Analytics"
        className="grid gap-6 lg:grid-cols-2"
      >
        <PresenceChart />
        <EventsChart />
      </section>

      <section aria-label="Recent activity">
        <TimelineFeed />
      </section>
    </div>
  );
}

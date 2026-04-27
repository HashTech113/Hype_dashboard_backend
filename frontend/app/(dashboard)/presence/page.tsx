"use client";

import { PresencePanel } from "@/components/presence/presence-panel";
import { LiveIndicator } from "@/components/shared/live-indicator";
import { usePresence } from "@/lib/hooks/use-presence";
import { useDashboardSnapshot } from "@/lib/hooks/use-dashboard";

export default function PresencePage() {
  const { data, isFetching, isError } = useDashboardSnapshot(30_000);
  const { dataUpdatedAt } = usePresence();
  const asOf = dataUpdatedAt
    ? new Date(dataUpdatedAt).toISOString()
    : data?.as_of ?? null;

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">
            Live presence
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Who is inside, outside, or on break right now.
          </p>
        </div>
        <LiveIndicator
          asOf={asOf}
          stale={isError || (!isFetching && !data)}
        />
      </header>

      <PresencePanel />
    </div>
  );
}

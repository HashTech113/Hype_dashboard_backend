"use client";

import { UserSearch } from "lucide-react";

import { ClusterCard } from "@/components/unknowns/cluster-card";
import { Skeleton } from "@/components/ui/skeleton";
import type { UnknownCluster } from "@/lib/types/unknowns";

interface ClusterGridProps {
  clusters: UnknownCluster[] | undefined;
  loading: boolean;
  onOpen: (cluster: UnknownCluster) => void;
}

export function ClusterGrid({ clusters, loading, onOpen }: ClusterGridProps) {
  if (loading && (!clusters || clusters.length === 0)) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="overflow-hidden rounded-lg border bg-card">
            <Skeleton className="aspect-square w-full" />
            <div className="space-y-2 p-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!clusters || clusters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed bg-card/50 px-6 py-16 text-center">
        <UserSearch className="h-10 w-10 text-muted-foreground" />
        <p className="mt-3 text-sm font-medium">No unknown faces yet</p>
        <p className="mt-1 max-w-md text-xs text-muted-foreground">
          When the cameras see a face that doesn&apos;t match any employee, it will
          appear here as a unique person you can review and add to the system.
          Make sure <span className="font-medium">unknown capture</span> is
          enabled in Settings.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {clusters.map((c) => (
        <ClusterCard key={c.id} cluster={c} onOpen={onOpen} />
      ))}
    </div>
  );
}

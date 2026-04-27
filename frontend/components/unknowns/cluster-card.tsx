"use client";

import { formatDistanceToNow } from "date-fns";
import { Images, Tag } from "lucide-react";

import { UnknownFaceImage } from "@/components/unknowns/unknown-face-image";
import { Badge } from "@/components/ui/badge";
import type { UnknownCluster, UnknownClusterStatus } from "@/lib/types/unknowns";
import { cn } from "@/lib/utils";

interface ClusterCardProps {
  cluster: UnknownCluster;
  onOpen: (cluster: UnknownCluster) => void;
}

const STATUS_VARIANT: Record<
  UnknownClusterStatus,
  "default" | "secondary" | "destructive" | "outline" | "success" | "warning"
> = {
  PENDING: "warning",
  PROMOTED: "success",
  IGNORED: "secondary",
  MERGED: "outline",
};

export function ClusterCard({ cluster, onOpen }: ClusterCardProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(cluster)}
      className={cn(
        "group flex flex-col overflow-hidden rounded-lg border bg-card text-left",
        "transition-all hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      <UnknownFaceImage
        captureId={cluster.representative_capture_id}
        className="aspect-square w-full"
        alt={cluster.label ?? `Unknown #${cluster.id}`}
      />
      <div className="flex flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              {cluster.label ?? (
                <span className="text-muted-foreground">
                  Unknown #{cluster.id}
                </span>
              )}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              Last seen {formatDistanceToNow(new Date(cluster.last_seen_at), { addSuffix: true })}
            </p>
          </div>
          <Badge variant={STATUS_VARIANT[cluster.status]}>{cluster.status}</Badge>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Images className="h-3.5 w-3.5" />
            {cluster.member_count} face{cluster.member_count === 1 ? "" : "s"}
          </span>
          {cluster.label && (
            <span className="inline-flex items-center gap-1">
              <Tag className="h-3.5 w-3.5" />
              labeled
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

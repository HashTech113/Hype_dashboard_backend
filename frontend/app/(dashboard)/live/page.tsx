"use client";

import { useMemo } from "react";
import { Camera as CameraIcon, Activity, AlertCircle } from "lucide-react";

import { CameraPreviewTile } from "@/components/cameras/camera-preview-tile";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { useCameras, useCamerasHealth } from "@/lib/hooks/use-cameras";
import type { CameraHealth } from "@/lib/types/camera";

export default function LiveViewPage() {
  const { data: cameras, isLoading } = useCameras();
  const { data: health } = useCamerasHealth(5_000);

  const healthById = useMemo(() => {
    const map = new Map<number, CameraHealth>();
    for (const h of health ?? []) map.set(h.id, h);
    return map;
  }, [health]);

  const summary = useMemo(() => {
    const list = cameras ?? [];
    // "Live" means we've received an actual frame recently — not just that
    // the worker thread is alive. Heartbeat-based "live" is misleading
    // because the worker keeps heartbeating even while RTSP fails silently.
    const live = (health ?? []).filter(
      (h) =>
        h.is_running &&
        !h.last_error &&
        h.last_frame_age_seconds !== null &&
        h.last_frame_age_seconds < 15,
    ).length;
    return { total: list.length, live };
  }, [cameras, health]);

  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-6">
      <PageHeader
        title="Live View"
        description="Real-time feed from every camera, with face boxes drawn over what the system sees. Green = recognized employee. Red = unknown person. The grid auto-refreshes every 1.5 s."
        actions={
          <div className="flex items-center gap-3 rounded-md border bg-card px-3 py-1.5 text-sm">
            <Activity className="h-4 w-4 text-success animate-pulse" />
            <span className="tabular-nums">
              <span className="font-medium">{summary.live}</span>
              <span className="text-muted-foreground">/{summary.total} live</span>
            </span>
          </div>
        }
      />

      {/* Legend */}
      <Card className="flex flex-wrap items-center gap-4 px-4 py-3 text-xs">
        <span className="font-medium uppercase tracking-wide text-muted-foreground">
          Legend
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-3 rounded-sm bg-green-500" />
          Recognized employee (label = name + match %)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-3 rounded-sm bg-red-500" />
          Unknown face (not in employee database)
        </span>
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          <AlertCircle className="h-3.5 w-3.5" />
          Faces appear once a frame is processed (≈1 second after they walk in)
        </span>
      </Card>

      {/* Tiles */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="aspect-video animate-pulse rounded-lg bg-muted"
            />
          ))}
        </div>
      ) : !cameras || cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-card/50 px-6 py-16 text-center">
          <CameraIcon className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium">No cameras configured yet</p>
          <p className="max-w-md text-xs text-muted-foreground">
            Add cameras on the <span className="font-medium">Cameras</span> page
            first — each one gets its own tile here.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-2">
          {cameras.map((c) => (
            <CameraPreviewTile
              key={c.id}
              camera={c}
              health={healthById.get(c.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

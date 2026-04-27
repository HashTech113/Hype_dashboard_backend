"use client";

import {
  Activity,
  AlertTriangle,
  Camera as CameraIcon,
  Clock,
  ImageOff,
  Loader2,
  PowerOff,
  RefreshCw,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCameraPreview, useRestartCamera } from "@/lib/hooks/use-cameras";
import type { Camera, CameraHealth } from "@/lib/types/camera";
import { cn } from "@/lib/utils";

interface Props {
  camera: Camera;
  health?: CameraHealth;
  refetchMs?: number;
}

const STALE_THRESHOLD_MS = 5_000;

export function CameraPreviewTile({
  camera,
  health,
  // Poll cadence — tuned to feel like ~real-time at the default
  // camera_fps=5. Bump it higher in Settings if you change camera FPS.
  refetchMs = 600,
}: Props) {
  // Skip polling when the camera is disabled — the backend would 404 anyway.
  const { url, error, updatedAt } = useCameraPreview(
    camera.is_active ? camera.id : null,
    refetchMs,
  );
  const restart = useRestartCamera();

  // Recompute "frame age" in real time so the tile feels alive even between
  // polls.
  const [, forceTick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => forceTick((x) => x + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  const ageMs = updatedAt ? Date.now() - updatedAt : null;
  const isStale = ageMs !== null && ageMs > STALE_THRESHOLD_MS;

  const status = computeStatus(camera, health, url, isStale, error);

  return (
    <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
      {/* Video panel */}
      <div className="relative aspect-video w-full bg-black">
        {url ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={url}
            alt={`${camera.name} preview`}
            className={cn(
              "h-full w-full object-contain transition-opacity",
              isStale && "opacity-50",
            )}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-white/70">
            {!camera.is_active ? (
              <div className="flex flex-col items-center gap-2 text-sm">
                <PowerOff className="h-8 w-8" />
                <span>Camera disabled</span>
              </div>
            ) : error ? (
              <div className="flex max-w-[80%] flex-col items-center gap-2 text-center text-sm">
                <AlertTriangle className="h-8 w-8 text-amber-400" />
                <span className="text-amber-200">{error}</span>
                <span className="text-xs text-white/50">
                  Worker will retry automatically
                </span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-sm">
                <Loader2 className="h-8 w-8 animate-spin" />
                <span>Connecting…</span>
              </div>
            )}
          </div>
        )}

        {/* Top-left: camera type */}
        <Badge
          variant={camera.camera_type === "ENTRY" ? "default" : "secondary"}
          className="absolute left-2 top-2"
        >
          {camera.camera_type}
        </Badge>

        {/* Top-right: live status */}
        <Badge variant={status.variant} className="absolute right-2 top-2 gap-1">
          {status.iconLeft}
          {status.label}
        </Badge>

        {/* Stalled overlay over a stale image */}
        {isStale && url && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-1 bg-amber-500/85 px-3 py-1 text-xs font-medium text-white">
            <AlertTriangle className="h-3.5 w-3.5" />
            Stream stalled — last frame {(ageMs! / 1000).toFixed(1)}s ago
          </div>
        )}
      </div>

      {/* Footer with details + actions */}
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <CameraIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate text-sm font-medium">
                {camera.name}
              </span>
            </div>
            {camera.location && (
              <p className="truncate text-xs text-muted-foreground">
                {camera.location}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            title="Restart worker"
            onClick={() => restart.mutate(camera.id)}
            disabled={!camera.is_active || restart.isPending}
          >
            {restart.isPending && restart.variables === camera.id ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground tabular-nums">
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {ageMs === null
              ? "—"
              : ageMs < 1000
                ? "just now"
                : `${(ageMs / 1000).toFixed(1)}s ago`}
          </span>
          {health?.last_error && (
            <span
              className="truncate text-destructive"
              title={health.last_error}
            >
              {health.last_error}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function computeStatus(
  camera: Camera,
  health: CameraHealth | undefined,
  url: string | null,
  isStale: boolean,
  error: string | null,
): {
  variant:
    | "default"
    | "secondary"
    | "destructive"
    | "outline"
    | "success"
    | "warning";
  label: string;
  iconLeft: React.ReactNode;
} {
  if (!camera.is_active) {
    return {
      variant: "secondary",
      label: "Disabled",
      iconLeft: <PowerOff className="h-3 w-3" />,
    };
  }
  if (health?.last_error) {
    return {
      variant: "destructive",
      label: "Error",
      iconLeft: <AlertTriangle className="h-3 w-3" />,
    };
  }
  if (health && !health.is_running) {
    return {
      variant: "warning",
      label: "Stopped",
      iconLeft: <AlertTriangle className="h-3 w-3" />,
    };
  }
  if (isStale) {
    return {
      variant: "warning",
      label: "Stale",
      iconLeft: <AlertTriangle className="h-3 w-3" />,
    };
  }
  if (url) {
    return {
      variant: "success",
      label: "Live",
      iconLeft: <Activity className="h-3 w-3 animate-pulse" />,
    };
  }
  if (error) {
    return {
      variant: "warning",
      label: "Reconnecting",
      iconLeft: <Loader2 className="h-3 w-3 animate-spin" />,
    };
  }
  return {
    variant: "outline",
    label: "Connecting",
    iconLeft: <Loader2 className="h-3 w-3 animate-spin" />,
  };
}

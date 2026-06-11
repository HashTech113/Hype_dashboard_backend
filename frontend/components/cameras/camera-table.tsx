"use client";

import { formatDistanceToNow } from "date-fns";
import {
  Activity,
  AlertTriangle,
  Loader2,
  MoreHorizontal,
  Pencil,
  PowerOff,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useRestartCamera } from "@/lib/hooks/use-cameras";
import type { Camera, CameraHealth } from "@/lib/types/camera";

interface CameraTableProps {
  cameras: Camera[] | undefined;
  health: CameraHealth[] | undefined;
  loading: boolean;
  onEdit: (cam: Camera) => void;
  onDelete: (cam: Camera) => void;
}

function maskRtsp(url: string): string {
  // Hide username:password in display while keeping the host visible
  return url.replace(/(rtsps?:\/\/)([^@/]+)@/i, "$1•••@");
}

export function CameraTable({
  cameras,
  health,
  loading,
  onEdit,
  onDelete,
}: CameraTableProps) {
  const healthById = useMemo(() => {
    const m = new Map<number, CameraHealth>();
    for (const h of health ?? []) m.set(h.id, h);
    return m;
  }, [health]);

  const restart = useRestartCamera();

  if (loading && (!cameras || cameras.length === 0)) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!cameras || cameras.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
        <p className="text-sm font-medium">No cameras configured yet</p>
        <p className="mt-1 max-w-md text-xs text-muted-foreground">
          Click <span className="font-medium">Add camera</span> above to register
          your first RTSP stream. The system will start a worker thread for it
          immediately.
        </p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[24%]">Name</TableHead>
          <TableHead>RTSP</TableHead>
          <TableHead>FPS</TableHead>
          <TableHead>Health</TableHead>
          <TableHead className="w-[60px]" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {cameras.map((cam) => {
          const h = healthById.get(cam.id);
          return (
            <TableRow key={cam.id}>
              <TableCell>
                <div className="flex flex-col">
                  <span className="font-medium">{cam.name}</span>
                  {cam.location && (
                    <span className="text-xs text-muted-foreground">
                      {cam.location}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <code
                  className="block max-w-[380px] truncate font-mono text-xs text-muted-foreground"
                  title={maskRtsp(cam.rtsp_url)}
                >
                  {maskRtsp(cam.rtsp_url)}
                </code>
              </TableCell>
              <TableCell>
                <FpsCell camera={cam} health={h} />
              </TableCell>
              <TableCell>
                <HealthCell camera={cam} health={h} />
              </TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-44">
                    <DropdownMenuItem onClick={() => onEdit(cam)}>
                      <Pencil className="mr-2 h-4 w-4" /> Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => restart.mutate(cam.id)}
                      disabled={!cam.is_active || restart.isPending}
                    >
                      {restart.isPending && restart.variables === cam.id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="mr-2 h-4 w-4" />
                      )}
                      Restart worker
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => onDelete(cam)}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="mr-2 h-4 w-4" /> Delete forever
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function FpsCell({
  camera,
  health,
}: {
  camera: Camera;
  health: CameraHealth | undefined;
}) {
  // Show the effective FPS (what the worker is actually running at) and
  // mark with "(override)" when set per-camera so it's obvious which
  // cameras are tuned individually.
  if (!camera.is_active) {
    return <span className="text-xs text-muted-foreground">&mdash;</span>;
  }
  const eff = health?.fps_effective ?? camera.fps_override ?? null;
  const isOverride = camera.fps_override !== null && camera.fps_override !== undefined;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-sm tabular-nums">
        {eff !== null ? `${eff} fps` : <span className="text-muted-foreground">global</span>}
      </span>
      {isOverride && (
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          override
        </span>
      )}
    </div>
  );
}

function HealthCell({
  camera,
  health,
}: {
  camera: Camera;
  health: CameraHealth | undefined;
}) {
  if (!camera.is_active) {
    return (
      <Badge variant="secondary" className="gap-1">
        <PowerOff className="h-3 w-3" />
        Disabled
      </Badge>
    );
  }
  if (!health) {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        Pending
      </Badge>
    );
  }
  // DEGRADED — too many consecutive open failures. Surface the count + the
  // last error so the operator knows what's wrong without opening logs.
  if (health.health_state === "DEGRADED") {
    return (
      <div className="flex flex-col gap-1">
        <Badge variant="destructive" className="gap-1">
          <AlertTriangle className="h-3 w-3" />
          Degraded
        </Badge>
        <span
          className="max-w-[260px] truncate text-[11px] text-destructive"
          title={health.last_error ?? undefined}
        >
          {health.last_error ?? `${health.consecutive_open_failures} open failures`}
        </span>
      </div>
    );
  }
  if (health.last_error) {
    return (
      <div className="flex flex-col gap-1">
        <Badge variant="destructive" className="gap-1">
          <AlertTriangle className="h-3 w-3" />
          Error
        </Badge>
        <span
          className="max-w-[260px] truncate text-[11px] text-destructive"
          title={health.last_error}
        >
          {health.last_error}
        </span>
        {health.total_reconnects > 0 && (
          <span className="text-[10px] text-muted-foreground">
            {health.total_reconnects} reconnect{health.total_reconnects === 1 ? "" : "s"}
          </span>
        )}
      </div>
    );
  }
  if (!health.is_running) {
    return (
      <Badge variant="warning" className="gap-1">
        <AlertTriangle className="h-3 w-3" />
        Stopped
      </Badge>
    );
  }
  // Critical: gate "Live" on the actual frame timestamp, NOT the heartbeat.
  // The heartbeat ticks every loop iteration even when RTSP reads silently
  // fail — relying on it produces false positives (showing "Live" when the
  // camera has never connected).
  const frameAge = health.last_frame_age_seconds; // null = never received
  if (frameAge === null) {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="warning" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          No video
        </Badge>
        <span className="max-w-[200px] truncate text-[11px] text-muted-foreground">
          worker alive, stream not connected
        </span>
      </div>
    );
  }
  if (frameAge > 15) {
    return (
      <div className="flex flex-col gap-0.5">
        <Badge variant="warning" className="gap-1">
          <AlertTriangle className="h-3 w-3" />
          Stale
        </Badge>
        <span className="text-[11px] text-muted-foreground">
          last frame{" "}
          {frameAge < 60
            ? `${frameAge.toFixed(1)}s ago`
            : formatDistanceToNow(new Date(Date.now() - frameAge * 1000), {
                addSuffix: true,
              })}
        </span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-0.5">
      <Badge variant="success" className="gap-1">
        <Activity className="h-3 w-3 animate-pulse" />
        Live
      </Badge>
      <span className="text-[11px] text-muted-foreground">
        last frame {frameAge.toFixed(1)}s ago
      </span>
    </div>
  );
}

"use client";

import {
  Activity,
  AlertTriangle,
  Camera as CameraIcon,
  Loader2,
  MoreHorizontal,
  Pencil,
  PowerOff,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import { CameraFormDialog } from "@/components/cameras/camera-form-dialog";
import { CameraWebRtcStream } from "@/components/cameras/camera-webrtc-stream";
import { CameraWsStream } from "@/components/cameras/camera-ws-stream";
import { DeleteCameraDialog } from "@/components/cameras/delete-camera-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useRestartCamera } from "@/lib/hooks/use-cameras";
import type { Camera, CameraHealth } from "@/lib/types/camera";
import { cn } from "@/lib/utils";

interface Props {
  camera: Camera;
  health?: CameraHealth;
  /** Deprecated — MJPEG streams continuously now. Kept for API compat. */
  refetchMs?: number;
}

export function CameraPreviewTile({
  camera,
  health,
}: Props) {
  const restart = useRestartCamera();
  // Track whether the stream has produced a first frame so the badge
  // flips from "Connecting" to "Live" without polling state.
  const [streamLive, setStreamLive] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [liveLagMs, setLiveLagMs] = useState<number | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  // Stream strategy: WebSocket JPEG is the PROVEN realtime path.
  //   1. Backend drain thread guarantees the freshest frame is sent
  //      (NEW — eliminates the 5+ second lag from accumulated FFmpeg buffer)
  //   2. WS backpressure (await send_bytes) prevents buffer build-up
  //   3. Sub-stream resolution + INTER_LINEAR resize keeps encode fast
  //   4. Face-detection boxes are server-rendered onto each JPEG
  // WebRTC via go2rtc is faster IN THEORY (50-100 ms) but its actual
  // latency depends on the camera's GOP — many cameras ship with 2.5s+
  // keyframe intervals causing multi-second initial delays. Until the
  // operator opts in via a "use WebRTC" toggle (and configures their
  // camera GOP=10 + Baseline profile), WS is the dependable choice.
  const useFallback = true;

  useEffect(() => {
    setStreamLive(false);
    setStreamError(false);
    setLiveLagMs(null);
  }, [camera.id, camera.is_active]);

  // Tick to keep the per-second "frame age" hint fresh on the footer.
  const [, forceTick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => forceTick((x) => x + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  // Frame-age is derived from the worker's last_frame_age_seconds (health).
  // We don't need a per-frame timestamp anymore — MJPEG streams continuously
  // and the backend's health endpoint reports staleness.
  const frameAgeMs = health?.last_frame_age_seconds != null
    ? Math.max(0, Math.floor(health.last_frame_age_seconds * 1000))
    : null;
  const isStale = frameAgeMs !== null && frameAgeMs > 5_000;

  const status = computeStatus(
    camera,
    health,
    streamLive,
    isStale,
    streamError,
  );

  return (
    <>
    <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
      {/* Video panel — MJPEG live stream */}
      <div className="relative aspect-video w-full bg-black">
        {/* Disabled cameras: show a centered "Delete this camera" CTA
            instead of the empty "Camera disabled" placeholder. This is
            the action the operator wants on /live — they don't need to
            navigate to /cameras to clean up stale entries. */}
        {!camera.is_active ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-muted/30 p-6 text-center">
            <PowerOff className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              This camera is disabled
            </p>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDeleteOpen(true)}
              className="gap-1.5"
            >
              <Trash2 className="h-4 w-4" />
              Delete this camera
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditOpen(true)}
              className="gap-1.5 text-xs"
            >
              <Pencil className="h-3.5 w-3.5" />
              Or edit details
            </Button>
          </div>
        ) : useFallback ? (
          <CameraWsStream
            cameraId={camera.id}
            isActive={camera.is_active}
            // Minimum-latency defaults: 640px at quality 60 produces
            // ~12-20 KB JPEGs that encode in <5 ms backend-side and
            // decode in <8 ms in the browser. Total per-frame budget
            // ~30 ms which lines up with the camera's native frame
            // interval at 20 fps (50 ms). Bumping to 854/70 makes face
            // boxes sharper but adds 10-15 ms of encode overhead.
            maxWidth={640}
            quality={60}
            className={cn("h-full w-full", isStale && "opacity-50")}
            alt={`${camera.name} live`}
            onFirstFrame={() => setStreamLive(true)}
            onStreamEnd={() => setStreamError(true)}
            onLatency={(ms) => setLiveLagMs(ms)}
          />
        ) : (
          <CameraWebRtcStream
            cameraId={camera.id}
            isActive={camera.is_active}
            className={cn("h-full w-full", isStale && "opacity-50")}
            alt={`${camera.name} live`}
            onFirstFrame={() => setStreamLive(true)}
            onStreamEnd={() => setStreamError(true)}
            onLatency={(ms) => setLiveLagMs(ms)}
            onUnavailable={() => {
              /* WebRTC branch is currently unreachable (useFallback=true
                 by default). When we re-enable WebRTC behind an opt-in
                 toggle, wire setUseFallback(true) back here. */
            }}
          />
        )}

        {/* Top-right: live status (the ENTRY/EXIT badge was removed —
            this is generic surveillance, not turnstile attendance) */}
        <Badge variant={status.variant} className="absolute right-2 top-2 gap-1">
          {status.iconLeft}
          {status.label}
        </Badge>

        {/* Camera-offline diagnostic overlay — replaces the generic
            "Reconnecting" spinner with actionable info when the BACKEND
            reports the worker can't reach the camera. Tells the
            operator: it's the camera that's down, the software is
            healthy, and what to physically check. */}
        {camera.is_active &&
          health &&
          !streamLive &&
          (health.health_state === "CONNECTING" ||
            health.health_state === "FLAPPING" ||
            health.health_state === "DEGRADED") && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/85 p-6 text-center text-white">
              <AlertTriangle className="h-8 w-8 text-amber-400" />
              <div className="space-y-1">
                <p className="text-sm font-semibold">
                  Camera not reachable
                </p>
                <p className="text-xs text-white/70">
                  {health.health_state === "DEGRADED"
                    ? `After ${health.consecutive_open_failures} failed attempts the worker is retrying every 60 s to spare CPU.`
                    : health.health_state === "FLAPPING"
                    ? `Connecting and disconnecting repeatedly — ${health.total_reconnects} reconnects so far.`
                    : `Trying to reconnect every 5 s — ${health.consecutive_open_failures} attempt(s) so far.`}
                </p>
                {health.last_error && (
                  <p className="mt-2 max-w-[90%] truncate text-[10px] font-mono text-white/50">
                    {health.last_error}
                  </p>
                )}
              </div>
              <div className="mt-2 text-[11px] text-white/60">
                <p>Check:</p>
                <ul className="mt-1 space-y-0.5 text-white/50">
                  <li>· Camera power LED is on</li>
                  <li>· Ethernet cable from camera → PoE switch → PC</li>
                  <li>· Camera IP hasn&apos;t changed (router DHCP page)</li>
                </ul>
              </div>
            </div>
          )}

        {/* Stalled overlay — backend reports frame_age but MJPEG keeps
            displaying the last frame. Show a warning band when the
            worker hasn't gotten a fresh frame for a few seconds. */}
        {isStale && streamLive && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-1 bg-amber-500/85 px-3 py-1 text-xs font-medium text-white">
            <AlertTriangle className="h-3.5 w-3.5" />
            Stream stalled — last frame{" "}
            {frameAgeMs !== null ? `${(frameAgeMs / 1000).toFixed(1)}s ago` : "unknown"}
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
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                title="Camera actions"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onClick={() => setEditOpen(true)}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit details
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => restart.mutate(camera.id)}
                disabled={!camera.is_active || restart.isPending}
              >
                {restart.isPending && restart.variables === camera.id ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Restart worker
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => setDeleteOpen(true)}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete forever
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground tabular-nums">
          {health?.fps_effective != null && (
            <span className="inline-flex items-center gap-1">
              <Activity className="h-3 w-3" />
              {health.fps_effective} fps
            </span>
          )}
          {/* Measured END-TO-END latency from the WebSocket stream —
              producer→display time as observed by THIS browser. This is
              the actual number that matches what your eyes see. */}
          {liveLagMs !== null && (
            <span
              className={cn(
                "inline-flex items-center gap-1",
                liveLagMs > 250 && "text-amber-600 dark:text-amber-500",
                liveLagMs > 500 && "text-destructive",
              )}
            >
              {liveLagMs}ms live lag
            </span>
          )}
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

    {/* Mounted at the end so the dialogs aren't constrained by the
        tile's overflow-hidden + aspect-ratio container. */}
    <CameraFormDialog
      open={editOpen}
      onOpenChange={setEditOpen}
      camera={camera}
    />
    <DeleteCameraDialog
      open={deleteOpen}
      onOpenChange={setDeleteOpen}
      camera={camera}
    />
    </>
  );
}

function computeStatus(
  camera: Camera,
  health: CameraHealth | undefined,
  streamLive: boolean,
  isStale: boolean,
  streamError: boolean,
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
  if (streamLive) {
    return {
      variant: "success",
      label: "Live",
      iconLeft: <Activity className="h-3 w-3 animate-pulse" />,
    };
  }
  if (streamError) {
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

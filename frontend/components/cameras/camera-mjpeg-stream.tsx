"use client";

/**
 * Native-realtime MJPEG stream component.
 *
 * Replaces the previous JPEG-polling preview. The browser's `<img>` tag
 * is given a multipart/x-mixed-replace URL — Chrome / Firefox / Safari
 * keep one HTTP connection open and decode incoming JPEG frames as fast
 * as the backend delivers them.
 *
 * End-to-end latency: ~80-150 ms (camera + FFmpeg buffer + JPEG encode +
 * TCP send + browser decode). Compare to JPEG polling at 200 ms intervals
 * which has a 200-400 ms ceiling.
 *
 * Auth: <img> can't set an Authorization header, so we rely on the
 * `aa_token` cookie which the browser sends automatically with the
 * subresource request. The JWT is intentionally NOT placed in the
 * query string — query params leak into browser history, server
 * access logs, proxy logs, and the Referer header.
 */

import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  cameraId: number;
  isActive: boolean;
  className?: string;
  imgClassName?: string;
  annotated?: boolean;
  quality?: number;
  maxFps?: number;
  /** Max frame width — smaller = lower bandwidth + smoother stream
   *  on slower CPUs. 854 (480p widescreen) for grid tiles, 1280 for
   *  full-tile single view, 1920 for a fullscreen modal. */
  maxWidth?: number;
  alt?: string;
  /** Called when the stream ends (camera stopped, error). */
  onStreamEnd?: () => void;
  /** Called the first time a frame loads, so the parent can drop spinners. */
  onFirstFrame?: () => void;
}

function buildApiUrl(): string {
  // process.env replacement happens at build time. The value comes from
  // `.env.local` (or whatever next.config.mjs settled on).
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

export function CameraMjpegStream({
  cameraId,
  isActive,
  className,
  imgClassName,
  annotated = true,
  quality = 70,
  maxFps = 30,
  maxWidth = 1280,
  alt = "Live camera stream",
  onStreamEnd,
  onFirstFrame,
}: Props) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  // Build the URL. Auth is provided by the `aa_token` cookie which the
  // browser sends automatically with the <img> subresource request.
  // If the cookie is missing (rare — user not logged in), the stream
  // endpoint will 401 and we'll show the error state.
  const streamUrl = useMemo(() => {
    if (!isActive) return null;
    const apiBase = buildApiUrl();
    const params = new URLSearchParams({
      annotated: annotated ? "true" : "false",
      quality: String(quality),
      max_fps: String(maxFps),
      max_width: String(maxWidth),
    });
    return `${apiBase}/cameras/${cameraId}/preview.mjpeg?${params.toString()}`;
  }, [cameraId, isActive, annotated, quality, maxFps, maxWidth]);

  useEffect(() => {
    // Reset visual state when the URL changes (camera swap).
    setLoaded(false);
    setErrored(false);
  }, [streamUrl]);

  // When the React component unmounts, force the <img> to drop its
  // connection by clearing the src. Without this, the browser may keep
  // the MJPEG socket open in the background until GC fires.
  useEffect(() => {
    return () => {
      if (imgRef.current) imgRef.current.src = "";
    };
  }, []);

  if (!isActive) {
    return (
      <div
        className={cn(
          "flex items-center justify-center bg-muted text-xs text-muted-foreground",
          className,
        )}
      >
        Camera disabled
      </div>
    );
  }

  if (errored) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-2 bg-muted text-xs text-muted-foreground",
          className,
        )}
      >
        <AlertTriangle className="h-4 w-4" />
        <span>Stream unavailable</span>
      </div>
    );
  }

  return (
    <div className={cn("relative overflow-hidden bg-black", className)}>
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={imgRef}
        src={streamUrl ?? undefined}
        alt={alt}
        className={cn(
          "h-full w-full object-contain transition-opacity",
          loaded ? "opacity-100" : "opacity-0",
          imgClassName,
        )}
        onLoad={() => {
          if (!loaded) {
            setLoaded(true);
            onFirstFrame?.();
          }
        }}
        onError={() => {
          setErrored(true);
          onStreamEnd?.();
        }}
      />
    </div>
  );
}

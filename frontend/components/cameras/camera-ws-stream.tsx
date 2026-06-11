"use client";

/**
 * True real-time WebSocket video stream with backpressure detection.
 *
 * The backend's WebSocket endpoint sends the next frame only AFTER the
 * previous one has been fully consumed by the browser's receive buffer.
 * That means there is NEVER a queue of stale frames waiting to be
 * displayed — what you see is the most recent frame the server produced
 * the moment it produced it.
 *
 * Wire format: each binary message is a 4-byte big-endian uint32 timestamp
 * (ms since worker start) + JPEG bytes. We decode via `createImageBitmap`
 * (off the main thread on modern Chrome) and draw to a <canvas>.
 *
 * If the round-trip ever drifts (browser tab backgrounded, CPU bound, etc.)
 * we DROP any frame older than 300 ms on receive — we never display stale
 * data even if it somehow arrives.
 */

import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  cameraId: number;
  isActive: boolean;
  className?: string;
  alt?: string;
  /** Max frame width — smaller = faster encode + decode. */
  maxWidth?: number;
  quality?: number;
  annotated?: boolean;
  /** Called once a frame is on the canvas. */
  onFirstFrame?: () => void;
  /** Called when the WS connection fails or closes unexpectedly. */
  onStreamEnd?: () => void;
  /** Receive the measured backend→display latency (ms) every frame. */
  onLatency?: (ms: number) => void;
}

const MAX_STALE_MS = 300;
const RECONNECT_BACKOFF_MS = 1000;

function buildApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

function buildWsUrl(cameraId: number, opts: {
  maxWidth: number;
  quality: number;
  annotated: boolean;
}): string {
  const httpUrl = buildApiUrl();
  // /api/v1 → ws(s)://host/api/v1
  const wsUrl = httpUrl.replace(/^http/, "ws");
  // Auth is provided by the `aa_token` cookie which the browser sends
  // automatically on the WebSocket handshake. We deliberately do NOT
  // place the JWT in the query string — query params leak into browser
  // history, server access logs, and proxy logs.
  const params = new URLSearchParams({
    annotated: opts.annotated ? "true" : "false",
    quality: String(opts.quality),
    max_width: String(opts.maxWidth),
  });
  return `${wsUrl}/cameras/${cameraId}/preview.ws?${params.toString()}`;
}

export function CameraWsStream({
  cameraId,
  isActive,
  className,
  alt = "Live camera stream",
  maxWidth = 854,
  quality = 70,
  annotated = true,
  onFirstFrame,
  onStreamEnd,
  onLatency,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const lastDrawTimeRef = useRef<number>(0);
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);

  // Keep the latest callback references in refs so the WebSocket effect
  // doesn't tear down and reconnect whenever the parent passes a new
  // function identity for these callbacks.
  const onFirstFrameRef = useRef(onFirstFrame);
  const onStreamEndRef = useRef(onStreamEnd);
  const onLatencyRef = useRef(onLatency);
  useEffect(() => {
    onFirstFrameRef.current = onFirstFrame;
    onStreamEndRef.current = onStreamEnd;
    onLatencyRef.current = onLatency;
  }, [onFirstFrame, onStreamEnd, onLatency]);

  useEffect(() => {
    if (!isActive) {
      setLoaded(false);
      setErrored(false);
      return;
    }
    let cancelled = false;
    let reconnectTimer: number | null = null;
    let serverEpochOffsetMs: number | null = null;

    function connect() {
      if (cancelled) return;
      const url = buildWsUrl(cameraId, { maxWidth, quality, annotated });
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) ws.close();
      };

      ws.onmessage = async (evt) => {
        if (cancelled) return;
        if (!(evt.data instanceof ArrayBuffer)) return;
        const buf = evt.data;
        if (buf.byteLength < 4) return;

        // The server header timestamp ticks from the worker's start.
        // Establish the offset from the FIRST frame, then measure how
        // much LARGER each subsequent ageOnArrival is — that's the
        // build-up. Min-lock the baseline so clock drift never goes
        // negative (which used to confuse the operator with "-90ms lag").
        const view = new DataView(buf);
        const frameMs = view.getUint32(0, false);
        const nowMs = performance.now();
        if (serverEpochOffsetMs === null) {
          // First frame defines the baseline. Treat its in-flight time
          // as ~0 ms, then later measurements are the *additional* drift.
          serverEpochOffsetMs = nowMs - frameMs;
        }
        // Implied wall-time the server produced this frame
        const producedAt = serverEpochOffsetMs + frameMs;
        const ageOnArrival = Math.max(0, nowMs - producedAt);

        // DROP stale frames on receive. If the network or the browser
        // had a hiccup and a frame is older than 300ms, skip it — show
        // the next fresh one instead.
        if (ageOnArrival > MAX_STALE_MS && lastDrawTimeRef.current > 0) {
          return;
        }

        // Decode JPEG → ImageBitmap (off main thread on Chrome).
        const jpegBytes = new Uint8Array(buf, 4);
        let bitmap: ImageBitmap;
        try {
          bitmap = await createImageBitmap(
            new Blob([jpegBytes], { type: "image/jpeg" }),
          );
        } catch {
          return;
        }
        if (cancelled) {
          bitmap.close();
          return;
        }

        const canvas = canvasRef.current;
        if (!canvas) {
          bitmap.close();
          return;
        }
        if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
        }
        const ctx = canvas.getContext("2d", { alpha: false });
        if (ctx) {
          ctx.drawImage(bitmap, 0, 0);
        }
        bitmap.close();
        lastDrawTimeRef.current = performance.now();

        // Report latency. We don't know the server's clock exactly so
        // this is producer→consumer time as observed by the client.
        if (onLatencyRef.current) onLatencyRef.current(Math.round(ageOnArrival));

        if (!loaded) {
          setLoaded(true);
          onFirstFrameRef.current?.();
        }
      };

      ws.onerror = () => {
        // onclose runs next; nothing to do here.
      };

      ws.onclose = () => {
        if (cancelled) return;
        onStreamEndRef.current?.();
        if (!loaded) setErrored(true);
        // Auto-reconnect after backoff; some cameras restart and the
        // server tears down the WS. Don't leave the user staring at a
        // dead tile.
        reconnectTimer = window.setTimeout(connect, RECONNECT_BACKOFF_MS);
      };
    }

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [cameraId, isActive, maxWidth, quality, annotated]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <canvas
        ref={canvasRef}
        aria-label={alt}
        className={cn(
          "h-full w-full object-contain transition-opacity",
          loaded ? "opacity-100" : "opacity-0",
        )}
      />
    </div>
  );
}

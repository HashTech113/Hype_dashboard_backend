"use client";

/**
 * True realtime live view using go2rtc's OWN battle-tested player.
 *
 * We stopped hand-rolling the WebRTC signalling — go2rtc ships its own
 * <video-stream> custom element (used by 100k+ Frigate installs) that
 * handles the full WebRTC → MSE → MJPEG fallback ladder natively. We
 * mount it directly here.
 *
 * The script files live at:
 *   /go2rtc/video-rtc.js     (base WebRTC class)
 *   /go2rtc/video-stream.js  (custom element wrapper)
 *
 * They were copied from the running go2rtc binary at first boot and are
 * served by Next.js as static assets. The middleware whitelists /go2rtc/*
 * so they're reachable without a login redirect.
 *
 * Latency floor: 50-100 ms (camera GOP + WebRTC transport + browser HW
 * decode). NO software re-encoding in this path.
 */

import { AlertTriangle, Loader2 } from "lucide-react";
import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import { camerasApi } from "@/lib/api/cameras";
import { cn } from "@/lib/utils";

// Declare the custom element so TS doesn't complain in JSX.
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "video-stream": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string;
          mode?: string;
          background?: boolean;
        },
        HTMLElement
      >;
    }
  }
}

type VideoStreamElement = HTMLElement & {
  src: string | URL;
  mode: string;
  background: boolean;
};

interface Props {
  cameraId: number;
  isActive: boolean;
  className?: string;
  alt?: string;
  onFirstFrame?: () => void;
  onStreamEnd?: () => void;
  onLatency?: (ms: number) => void;
  /** Called if go2rtc isn't reachable so parent can fall back to WS. */
  onUnavailable?: () => void;
  /** Show a small connection-state badge for debugging. */
  showDebugBadge?: boolean;
}

type ConnState =
  | "loading-info"
  | "loading-script"
  | "connecting"
  | "live"
  | "error";

export function CameraWebRtcStream({
  cameraId,
  isActive,
  className,
  alt = "Live camera stream",
  onFirstFrame,
  onStreamEnd,
  onLatency,
  onUnavailable,
  showDebugBadge = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const elementRef = useRef<VideoStreamElement | null>(null);
  const [state, setState] = useState<ConnState>("loading-info");
  const [stateDetail, setStateDetail] = useState<string>("");

  useEffect(() => {
    if (!isActive) return;
    let cancelled = false;
    let scriptCheckTimer: number | null = null;
    let watchdog: number | null = null;
    let detached = false;

    async function start() {
      setState("loading-info");
      setStateDetail("fetching webrtc info");
      // 1. Ask backend if go2rtc is up and get the signalling URL
      let info;
      try {
        info = await camerasApi.webrtcInfo(cameraId);
      } catch (e) {
        if (cancelled) return;
        setState("error");
        setStateDetail("go2rtc unavailable — falling back");
        // eslint-disable-next-line no-console
        console.warn("[webrtc] /webrtc-info failed:", e);
        onUnavailable?.();
        return;
      }
      if (cancelled) return;
      setStateDetail(`url=${new URL(info.webrtc_url).host}`);

      // 2. Wait for the go2rtc player script to finish loading (defined
      //    custom element). The <Script> tag below loads it; we just
      //    spin-wait until customElements.get('video-stream') is truthy.
      setState("loading-script");
      const scriptReady = await new Promise<boolean>((resolve) => {
        let elapsed = 0;
        scriptCheckTimer = window.setInterval(() => {
          if (cancelled) {
            resolve(false);
            return;
          }
          if (customElements.get("video-stream")) {
            resolve(true);
            return;
          }
          elapsed += 100;
          if (elapsed > 5000) {
            resolve(false);
          }
        }, 100);
      });
      if (scriptCheckTimer) window.clearInterval(scriptCheckTimer);
      if (cancelled) return;
      if (!scriptReady) {
        setState("error");
        setStateDetail("player script failed to load");
        // eslint-disable-next-line no-console
        console.warn("[webrtc] custom element 'video-stream' never registered");
        onUnavailable?.();
        return;
      }

      // 3. Mount the <video-stream> custom element. It does WebRTC + ICE
      //    + media playback for us. Setting src triggers connection.
      setState("connecting");
      setStateDetail("WebRTC negotiation in progress");
      const el = document.createElement("video-stream") as VideoStreamElement;
      // mode="webrtc" forces WebRTC only — element will try MSE/MJPEG
      // fallback otherwise but those are higher latency. We want to KNOW
      // if WebRTC failed so we can fall back to OUR WebSocket JPEG
      // (which respects auth + has face boxes drawn).
      el.mode = "webrtc";
      el.background = true; // keeps playing when tab is hidden
      el.src = info.webrtc_url;
      el.style.width = "100%";
      el.style.height = "100%";
      el.style.display = "block";

      // Listen for play events on the inner <video> the custom element
      // creates. We watch the container for it being inserted.
      const container = containerRef.current;
      if (!container) return;
      container.appendChild(el);
      elementRef.current = el;

      // Poll for first paint and connection state.
      let playing = false;
      const tickStart = performance.now();
      watchdog = window.setInterval(() => {
        if (cancelled || detached) {
          if (watchdog) window.clearInterval(watchdog);
          return;
        }
        const innerVideo = el.querySelector("video");
        if (!innerVideo) return;
        const hasFrame =
          innerVideo.readyState >= 2 &&
          innerVideo.videoWidth > 0 &&
          !innerVideo.paused;
        if (hasFrame && !playing) {
          playing = true;
          setState("live");
          setStateDetail("");
          onFirstFrame?.();
        }
        // 8-second watchdog: if no frame yet, declare WebRTC dead and
        // let the tile fall back to WebSocket.
        if (!playing && performance.now() - tickStart > 8000) {
          setState("error");
          setStateDetail("no video within 8s — falling back to WS");
          // eslint-disable-next-line no-console
          console.warn("[webrtc] watchdog timeout — falling back to WS");
          if (watchdog) window.clearInterval(watchdog);
          onUnavailable?.();
        }
      }, 250);
    }

    void start();

    return () => {
      cancelled = true;
      detached = true;
      if (scriptCheckTimer) window.clearInterval(scriptCheckTimer);
      if (watchdog) window.clearInterval(watchdog);
      try {
        const el = elementRef.current;
        if (el && el.parentNode) {
          // The custom element exposes a `disconnect` method that closes
          // the WebRTC peer + the signalling WS. Calling remove() also
          // triggers its disconnectedCallback() which does the cleanup.
          el.remove();
        }
      } catch {
        /* ignore */
      }
    };
  }, [cameraId, isActive]); // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
    <>
      {/* Load go2rtc's player scripts. type="module" because video-stream.js
          does `import {VideoRTC} from './video-rtc.js'`. */}
      <Script
        type="module"
        src="/go2rtc/video-stream.js"
        strategy="afterInteractive"
      />

      <div
        ref={containerRef}
        className={cn("relative overflow-hidden bg-black", className)}
      >
        {state !== "live" && state !== "error" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            {showDebugBadge && (
              <span className="text-xs">
                {state}
                {stateDetail ? ` — ${stateDetail}` : ""}
              </span>
            )}
          </div>
        )}
        {state === "error" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-xs text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            <span>{stateDetail || "WebRTC unavailable"}</span>
          </div>
        )}
        {showDebugBadge && state === "live" && (
          <span className="absolute left-2 top-2 z-10 rounded bg-green-600/90 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            WebRTC
          </span>
        )}
      </div>
    </>
  );
}

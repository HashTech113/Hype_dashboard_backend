"use client";

import { format, formatDistanceToNowStrict, parseISO } from "date-fns";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

interface LiveIndicatorProps {
  asOf?: string | null;
  stale?: boolean;
  className?: string;
}

export function LiveIndicator({ asOf, stale, className }: LiveIndicatorProps) {
  const [label, setLabel] = useState("");

  useEffect(() => {
    if (!asOf) {
      setLabel("");
      return;
    }
    const tick = () => {
      try {
        const dt = parseISO(asOf);
        setLabel(formatDistanceToNowStrict(dt, { addSuffix: true }));
      } catch {
        setLabel(asOf);
      }
    };
    tick();
    const id = setInterval(tick, 15_000);
    return () => clearInterval(id);
  }, [asOf]);

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border bg-card/60 px-3 py-1 text-xs",
        className,
      )}
      title={asOf ? `As of ${format(parseISO(asOf), "PPpp")}` : undefined}
    >
      <span className="relative flex h-2 w-2">
        {!stale && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
        )}
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            stale ? "bg-muted-foreground" : "bg-success",
          )}
        />
      </span>
      <span className="font-medium">{stale ? "Idle" : "Live"}</span>
      {label && <span className="text-muted-foreground">· {label}</span>}
    </div>
  );
}

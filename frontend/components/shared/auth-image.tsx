"use client";

import { ImageOff } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useSnapshotUrl } from "@/lib/hooks/use-attendance";
import { cn } from "@/lib/utils";

interface AuthImageProps {
  eventId: number;
  className?: string;
  imgClassName?: string;
  alt?: string;
  fallbackLabel?: string;
}

export function AuthImage({
  eventId,
  className,
  imgClassName,
  alt,
  fallbackLabel,
}: AuthImageProps) {
  const { url, loading, error } = useSnapshotUrl(eventId);

  return (
    <div
      className={cn(
        "relative overflow-hidden bg-muted",
        className,
      )}
    >
      {loading ? (
        <Skeleton className="absolute inset-0" />
      ) : error || !url ? (
        <div className="flex h-full w-full items-center justify-center gap-2 p-2 text-xs text-muted-foreground">
          <ImageOff className="h-4 w-4" />
          <span className="truncate">{fallbackLabel ?? "unavailable"}</span>
        </div>
      ) : (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          src={url}
          alt={alt ?? "Snapshot"}
          className={cn("h-full w-full object-cover", imgClassName)}
          loading="lazy"
          decoding="async"
        />
      )}
    </div>
  );
}

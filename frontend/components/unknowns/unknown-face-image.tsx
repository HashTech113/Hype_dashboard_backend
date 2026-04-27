"use client";

import { ImageOff } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useUnknownCaptureUrl } from "@/lib/hooks/use-unknowns";
import { cn } from "@/lib/utils";

interface UnknownFaceImageProps {
  captureId: number | null;
  className?: string;
  imgClassName?: string;
  alt?: string;
  fallbackLabel?: string;
}

export function UnknownFaceImage({
  captureId,
  className,
  imgClassName,
  alt,
  fallbackLabel,
}: UnknownFaceImageProps) {
  const { url, loading, error } = useUnknownCaptureUrl(captureId);

  return (
    <div className={cn("relative overflow-hidden bg-muted", className)}>
      {!captureId ? (
        <div className="flex h-full w-full items-center justify-center gap-2 p-2 text-xs text-muted-foreground">
          <ImageOff className="h-4 w-4" />
          <span className="truncate">{fallbackLabel ?? "no image"}</span>
        </div>
      ) : loading ? (
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
          alt={alt ?? "Unknown face"}
          className={cn("h-full w-full object-cover", imgClassName)}
          loading="lazy"
          decoding="async"
        />
      )}
    </div>
  );
}

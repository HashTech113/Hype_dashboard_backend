"use client";

import { format, parseISO } from "date-fns";
import { ImageOff, Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteFaceImage, useFaceImages } from "@/lib/hooks/use-training";

interface Props {
  employeeId: number;
}

export function FaceImageGallery({ employeeId }: Props) {
  const { data, isLoading } = useFaceImages(employeeId);
  const deleteMut = useDeleteFaceImage();

  if (isLoading) {
    return (
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="aspect-square w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed py-10 text-sm text-muted-foreground">
        <ImageOff className="h-5 w-5" />
        No training images enrolled yet.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
      {data.map((img) => {
        const pending =
          deleteMut.isPending && deleteMut.variables?.imageId === img.id;
        const fileLabel = img.file_path.split(/[\\/]/).pop() ?? "image";
        return (
          <div
            key={img.id}
            className="group relative aspect-square overflow-hidden rounded-md border bg-muted"
            title={`${fileLabel}\n${format(parseISO(img.created_at), "PPpp")}`}
          >
            <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
              <span className="truncate px-2 text-center">{fileLabel}</span>
            </div>
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-background/90 px-2 py-1 text-[10px]">
              <span className="tabular-nums">
                {img.width && img.height ? `${img.width}×${img.height}` : "—"}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-destructive hover:text-destructive"
                disabled={pending}
                onClick={() =>
                  deleteMut.mutate({ employeeId, imageId: img.id })
                }
                aria-label="Remove"
              >
                {pending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

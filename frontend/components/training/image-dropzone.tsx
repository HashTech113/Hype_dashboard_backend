"use client";

import { ImagePlus, Loader2, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const ACCEPT = "image/jpeg,image/png,image/webp";
const MAX_SIZE_MB = 10;

interface Props {
  min: number;
  max: number;
  submitting: boolean;
  onSubmit: (files: File[], replace: boolean) => void;
  disabled?: boolean;
}

interface QueuedFile {
  file: File;
  url: string;
}

export function ImageDropzone({
  min,
  max,
  submitting,
  onSubmit,
  disabled,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<QueuedFile[]>([]);
  const [replace, setReplace] = useState(false);
  const [drag, setDrag] = useState(false);

  useEffect(() => {
    return () => {
      for (const f of files) URL.revokeObjectURL(f.url);
    };
  }, [files]);

  const addFiles = useCallback(
    (incoming: FileList | File[]) => {
      const next: QueuedFile[] = [];
      for (const f of Array.from(incoming)) {
        if (!f.type.startsWith("image/")) continue;
        if (f.size > MAX_SIZE_MB * 1024 * 1024) continue;
        next.push({ file: f, url: URL.createObjectURL(f) });
      }
      setFiles((prev) => {
        const combined = [...prev, ...next];
        if (combined.length > max) {
          for (const f of combined.slice(max)) URL.revokeObjectURL(f.url);
        }
        return combined.slice(0, max);
      });
    },
    [max],
  );

  function removeAt(index: number) {
    setFiles((prev) => {
      const removed = prev[index];
      if (removed) URL.revokeObjectURL(removed.url);
      return prev.filter((_, i) => i !== index);
    });
  }

  function clearAll() {
    for (const f of files) URL.revokeObjectURL(f.url);
    setFiles([]);
  }

  const canSubmit = files.length >= min && files.length <= max && !submitting && !disabled;

  const hint = useMemo(() => {
    if (files.length === 0) return `Add ${min}–${max} images`;
    if (files.length < min) return `${min - files.length} more required`;
    return `${files.length} / ${max} selected`;
  }, [files.length, min, max]);

  return (
    <div className="space-y-4">
      <label
        htmlFor="training-file-input"
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (disabled || submitting) return;
          addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed bg-muted/20 p-8 text-center transition-colors",
          drag ? "border-primary bg-primary/5" : "border-border",
          (disabled || submitting) && "cursor-not-allowed opacity-60",
          !(disabled || submitting) && "cursor-pointer hover:bg-muted/40",
        )}
      >
        <UploadCloud className="h-8 w-8 text-muted-foreground" />
        <p className="text-sm font-medium">Drop images here, or click to browse</p>
        <p className="text-xs text-muted-foreground">
          JPEG / PNG / WebP · max {MAX_SIZE_MB} MB each · {min}–{max} images
        </p>
        <input
          id="training-file-input"
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          disabled={disabled || submitting}
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            if (inputRef.current) inputRef.current.value = "";
          }}
        />
      </label>

      {files.length > 0 && (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {files.map((f, i) => (
            <div
              key={`${f.file.name}-${i}`}
              className="group relative aspect-square overflow-hidden rounded-md border bg-muted"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={f.url}
                alt={f.file.name}
                className="h-full w-full object-cover"
              />
              <button
                type="button"
                aria-label="Remove"
                disabled={submitting}
                onClick={() => removeAt(i)}
                className="absolute right-1.5 top-1.5 rounded-full bg-background/80 p-1 text-foreground opacity-0 shadow transition-opacity hover:bg-background focus:opacity-100 group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
        <div className="flex items-center gap-4">
          <p className="text-xs text-muted-foreground">{hint}</p>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 accent-primary"
              checked={replace}
              onChange={(e) => setReplace(e.target.checked)}
              disabled={submitting}
            />
            Replace all existing images
          </label>
        </div>
        <div className="flex items-center gap-2">
          {files.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={clearAll}
              disabled={submitting}
            >
              Clear
            </Button>
          )}
          <Button
            type="button"
            onClick={() => {
              onSubmit(
                files.map((f) => f.file),
                replace,
              );
              if (replace) clearAll();
            }}
            disabled={!canSubmit}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ImagePlus className="h-4 w-4" />
            )}
            {submitting ? "Uploading…" : "Enroll images"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export { Label };

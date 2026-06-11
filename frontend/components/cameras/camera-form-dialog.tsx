"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  TestTube2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateCamera,
  useProbeCamera,
  useUpdateCamera,
} from "@/lib/hooks/use-cameras";
import type {
  Camera,
  CameraCreate,
  CameraProbeResult,
  CameraType,
  CameraUpdate,
} from "@/lib/types/camera";
import { cn } from "@/lib/utils";

const RTSP_REGEX = /^(rtsp|rtsps|http|https):\/\//i;

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(128),
  rtsp_url: z
    .string()
    .trim()
    .min(1, "RTSP URL is required")
    .max(1024)
    .refine(
      (v) => RTSP_REGEX.test(v),
      "Must start with rtsp://, rtsps://, http:// or https://",
    ),
  camera_type: z.enum(["ENTRY", "EXIT"]),
  location: z.string().trim().max(256).optional().or(z.literal("")),
  description: z.string().trim().max(1024).optional().or(z.literal("")),
  is_active: z.boolean(),
  // "" means inherit the global FPS; numeric overrides 1..30.
  fps_override: z
    .string()
    .optional()
    .refine(
      (v) => !v || (/^\d+$/.test(v) && +v >= 1 && +v <= 30),
      "FPS must be between 1 and 30 (or blank to inherit the global setting)",
    ),
});

type Values = z.infer<typeof schema>;

interface CameraFormDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  camera: Camera | null;
}

function toUndef(v: string | undefined): string | undefined {
  return v && v.length > 0 ? v : undefined;
}

export function CameraFormDialog({
  open,
  onOpenChange,
  camera,
}: CameraFormDialogProps) {
  const isEdit = camera !== null;
  const create = useCreateCamera();
  const update = useUpdateCamera();
  const probe = useProbeCamera();

  const [probeResult, setProbeResult] = useState<CameraProbeResult | null>(null);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      rtsp_url: "",
      camera_type: "ENTRY" as CameraType,
      location: "",
      description: "",
      is_active: true,
      fps_override: "",
    },
  });

  useEffect(() => {
    if (open) {
      setProbeResult(null);
      if (camera) {
        form.reset({
          name: camera.name,
          rtsp_url: camera.rtsp_url,
          camera_type: camera.camera_type,
          location: camera.location ?? "",
          description: camera.description ?? "",
          is_active: camera.is_active,
          fps_override: camera.fps_override ? String(camera.fps_override) : "",
        });
      } else {
        form.reset({
          name: "",
          rtsp_url: "",
          camera_type: "ENTRY",
          location: "",
          description: "",
          is_active: true,
          fps_override: "",
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, camera?.id]);

  const submitting = create.isPending || update.isPending;
  const errors = form.formState.errors;

  function handleProbe() {
    setProbeResult(null);
    const url = form.getValues("rtsp_url").trim();
    if (!url || !RTSP_REGEX.test(url)) {
      form.setError("rtsp_url", { message: "Enter a valid URL first" });
      return;
    }
    probe.mutate(
      { rtsp_url: url, timeout_ms: 8000 },
      {
        onSuccess: (res) => setProbeResult(res),
      },
    );
  }

  function handleSubmit(values: Values) {
    const fps = values.fps_override?.trim();
    const payload = {
      name: values.name.trim(),
      rtsp_url: values.rtsp_url.trim(),
      camera_type: values.camera_type,
      location: toUndef(values.location) ?? null,
      description: toUndef(values.description) ?? null,
      is_active: values.is_active,
      fps_override: fps ? +fps : null,
    };
    if (isEdit && camera) {
      update.mutate(
        { id: camera.id, payload: payload as CameraUpdate },
        { onSuccess: () => onOpenChange(false) },
      );
    } else {
      create.mutate(payload as CameraCreate, {
        onSuccess: () => onOpenChange(false),
      });
    }
  }

  // Heuristic — warn if the URL has an unencoded `@` in the password segment.
  // The backend auto-fixes this, but a heads-up here saves operator confusion.
  const url = form.watch("rtsp_url") ?? "";
  const atCount = (url.match(/@/g) || []).length;
  const showAtWarning = atCount > 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit camera" : "Add camera"}</DialogTitle>
          <DialogDescription>
            CP Plus / Dahua URL format: <code className="rounded bg-muted px-1 py-0.5 text-xs">{`rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=1`}</code>
            <br />
            Tip: if the password contains <code className="text-xs">@</code>, replace it with <code className="text-xs">%40</code>.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit(handleSubmit)}
          className="space-y-4"
          noValidate
        >
          <div className="grid grid-cols-1 gap-4">
            <Field label="Name" required error={errors.name?.message}>
              <Input
                placeholder="Office cam 1, Front door, Reception …"
                autoFocus
                {...form.register("name")}
                disabled={submitting}
              />
            </Field>
          </div>

          <Field label="RTSP URL" required error={errors.rtsp_url?.message}>
            <div className="flex gap-2">
              <Input
                placeholder="rtsp://admin:Admin%40123@192.168.1.101:554/cam/realmonitor?channel=1&subtype=1"
                {...form.register("rtsp_url")}
                disabled={submitting}
                onChange={(e) => {
                  form.register("rtsp_url").onChange(e);
                  setProbeResult(null);
                }}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleProbe}
                disabled={probe.isPending || submitting}
              >
                {probe.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <TestTube2 className="h-4 w-4" />
                )}
                Test
              </Button>
            </div>
            {showAtWarning && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                Heads up — your URL has more than one <code className="text-xs">@</code>.
                We&apos;ll automatically percent-encode the <code className="text-xs">@</code> in your password to <code className="text-xs">%40</code> on save.
              </p>
            )}
          </Field>

          {probeResult && (
            <div
              className={cn(
                "flex items-start gap-2 rounded-md border p-3 text-xs",
                probeResult.ok
                  ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300"
                  : "border-destructive/40 bg-destructive/10 text-destructive",
              )}
            >
              {probeResult.ok ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <div className="space-y-0.5">
                {probeResult.ok ? (
                  <>
                    <p className="font-medium">Stream reachable</p>
                    <p>
                      Resolution: {probeResult.width}×{probeResult.height} •
                      Connect time: {probeResult.elapsed_ms} ms
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-medium">Probe failed</p>
                    <p>{probeResult.error ?? "Unknown error"}</p>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Location">
              <Input
                placeholder="Front door, ground floor"
                {...form.register("location")}
                disabled={submitting}
              />
            </Field>
            <Field
              label="FPS override"
              error={errors.fps_override?.message as string | undefined}
            >
              <Input
                type="number"
                inputMode="numeric"
                min={1}
                max={30}
                placeholder="(use global)"
                {...form.register("fps_override")}
                disabled={submitting}
              />
              <p className="text-[11px] text-muted-foreground">
                1&ndash;30 fps. Blank = inherit global setting. Lower for low-traffic doors.
              </p>
            </Field>
            <Field label="Status">
              <label className="mt-2 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-input accent-primary"
                  {...form.register("is_active")}
                  disabled={submitting}
                />
                Active
              </label>
            </Field>
          </div>

          <Field label="Description">
            <Textarea
              placeholder="Optional notes — angle, mounting, model, etc."
              rows={2}
              {...form.register("description")}
              disabled={submitting}
            />
          </Field>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {isEdit ? "Save changes" : "Add camera"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label
        className={cn(
          required && "after:ml-0.5 after:text-destructive after:content-['*']",
        )}
      >
        {label}
      </Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { format, parseISO } from "date-fns";
import { Loader2, RotateCcw, Save } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useUpdateSettings } from "@/lib/hooks/use-settings";
import type { Settings } from "@/lib/types/settings";
import { cn } from "@/lib/utils";

const schema = z
  .object({
    work_start_time: z
      .string()
      .regex(/^\d{2}:\d{2}(:\d{2})?$/, "Use HH:MM")
      .or(z.literal("")),
    work_end_time: z
      .string()
      .regex(/^\d{2}:\d{2}(:\d{2})?$/, "Use HH:MM")
      .or(z.literal("")),
    grace_minutes: z.coerce.number().int().min(0).max(120),
    early_exit_grace_minutes: z.coerce.number().int().min(0).max(120),

    face_match_threshold: z.coerce
      .number()
      .gt(0, "Must be > 0")
      .lt(1, "Must be < 1"),
    face_min_quality: z.coerce.number().min(0).max(1),
    cooldown_seconds: z.coerce.number().int().min(0).max(300),

    camera_fps: z.coerce.number().int().min(1).max(30),
    train_min_images: z.coerce.number().int().min(1).max(100),
    train_max_images: z.coerce.number().int().min(1).max(100),

    auto_update_enabled: z.boolean(),
    auto_update_threshold: z.coerce
      .number()
      .gt(0, "Must be > 0")
      .lt(1, "Must be < 1"),
    auto_update_cooldown_seconds: z.coerce
      .number()
      .int()
      .min(60)
      .max(86400),
  })
  .refine((d) => d.train_max_images >= d.train_min_images, {
    message: "Max images must be ≥ min images",
    path: ["train_max_images"],
  })
  .refine(
    (d) =>
      !d.work_start_time ||
      !d.work_end_time ||
      d.work_end_time > d.work_start_time,
    {
      message: "Work end must be after work start",
      path: ["work_end_time"],
    },
  );

type Values = z.infer<typeof schema>;

function hhmm(value: string | null): string {
  if (!value) return "";
  // accepts "HH:MM" or "HH:MM:SS" — returns "HH:MM"
  return value.slice(0, 5);
}

function toHHMMSS(value: string): string | null {
  if (!value) return null;
  if (/^\d{2}:\d{2}$/.test(value)) return `${value}:00`;
  return value;
}

function toValues(s: Settings): Values {
  return {
    work_start_time: hhmm(s.work_start_time),
    work_end_time: hhmm(s.work_end_time),
    grace_minutes: s.grace_minutes,
    early_exit_grace_minutes: s.early_exit_grace_minutes,
    face_match_threshold: s.face_match_threshold,
    face_min_quality: s.face_min_quality,
    cooldown_seconds: s.cooldown_seconds,
    camera_fps: s.camera_fps,
    train_min_images: s.train_min_images,
    train_max_images: s.train_max_images,
    auto_update_enabled: s.auto_update_enabled,
    auto_update_threshold: s.auto_update_threshold,
    auto_update_cooldown_seconds: s.auto_update_cooldown_seconds,
  };
}

interface Props {
  initial: Settings;
}

export function SettingsForm({ initial }: Props) {
  const mut = useUpdateSettings();

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(initial),
  });

  useEffect(() => {
    form.reset(toValues(initial));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.updated_at]);

  const { errors, isDirty, dirtyFields } = form.formState;
  const autoUpdateEnabled = form.watch("auto_update_enabled");

  function submit(values: Values) {
    mut.mutate(
      {
        work_start_time: toHHMMSS(values.work_start_time) ?? undefined,
        work_end_time: toHHMMSS(values.work_end_time) ?? undefined,
        grace_minutes: values.grace_minutes,
        early_exit_grace_minutes: values.early_exit_grace_minutes,
        face_match_threshold: values.face_match_threshold,
        face_min_quality: values.face_min_quality,
        cooldown_seconds: values.cooldown_seconds,
        camera_fps: values.camera_fps,
        train_min_images: values.train_min_images,
        train_max_images: values.train_max_images,
        auto_update_enabled: values.auto_update_enabled,
        auto_update_threshold: values.auto_update_threshold,
        auto_update_cooldown_seconds: values.auto_update_cooldown_seconds,
      },
      {
        onSuccess: (saved) => form.reset(toValues(saved)),
      },
    );
  }

  function resetToServer() {
    form.reset(toValues(initial));
  }

  return (
    <form onSubmit={form.handleSubmit(submit)} className="flex flex-col gap-6" noValidate>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Office hours &amp; thresholds</CardTitle>
          <CardDescription>
            When the workday starts and ends, and how much grace before someone
            is flagged as late or an early exit.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Field
            label="Work start"
            error={errors.work_start_time?.message}
            dirty={dirtyFields.work_start_time}
          >
            <Input
              type="time"
              {...form.register("work_start_time")}
              disabled={mut.isPending}
            />
          </Field>
          <Field
            label="Work end"
            error={errors.work_end_time?.message}
            dirty={dirtyFields.work_end_time}
          >
            <Input
              type="time"
              {...form.register("work_end_time")}
              disabled={mut.isPending}
            />
          </Field>
          <Field
            label="Late grace (minutes)"
            hint="How late someone can arrive without being flagged."
            error={errors.grace_minutes?.message}
            dirty={dirtyFields.grace_minutes}
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              max={120}
              step={1}
              {...form.register("grace_minutes")}
              disabled={mut.isPending}
            />
          </Field>
          <Field
            label="Early exit grace (minutes)"
            hint="How early someone can leave without being flagged."
            error={errors.early_exit_grace_minutes?.message}
            dirty={dirtyFields.early_exit_grace_minutes}
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              max={120}
              step={1}
              {...form.register("early_exit_grace_minutes")}
              disabled={mut.isPending}
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recognition</CardTitle>
          <CardDescription>
            Face match confidence, minimum face quality for training, and the
            per-employee cooldown between detections.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Field
            label="Match threshold"
            hint="Cosine similarity · 0.00–1.00. Lower = more permissive."
            error={errors.face_match_threshold?.message}
            dirty={dirtyFields.face_match_threshold}
          >
            <Input
              type="number"
              inputMode="decimal"
              min={0.01}
              max={0.99}
              step={0.01}
              {...form.register("face_match_threshold")}
              disabled={mut.isPending}
            />
          </Field>
          <Field
            label="Min face quality"
            hint="Detector score floor for training images."
            error={errors.face_min_quality?.message}
            dirty={dirtyFields.face_min_quality}
          >
            <Input
              type="number"
              inputMode="decimal"
              min={0}
              max={1}
              step={0.01}
              {...form.register("face_min_quality")}
              disabled={mut.isPending}
            />
          </Field>
          <Field
            label="Cooldown (seconds)"
            hint="Global per-employee dedupe window."
            error={errors.cooldown_seconds?.message}
            dirty={dirtyFields.cooldown_seconds}
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              max={300}
              step={1}
              {...form.register("cooldown_seconds")}
              disabled={mut.isPending}
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Training &amp; camera pipeline</CardTitle>
          <CardDescription>
            Enrollment limits, capture frame-rate, and optional auto-update of
            embeddings when recognition is highly confident.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Field
              label="Camera FPS"
              hint="Frames per second per camera (1–30)."
              error={errors.camera_fps?.message}
              dirty={dirtyFields.camera_fps}
            >
              <Input
                type="number"
                inputMode="numeric"
                min={1}
                max={30}
                step={1}
                {...form.register("camera_fps")}
                disabled={mut.isPending}
              />
            </Field>
            <Field
              label="Min training images"
              error={errors.train_min_images?.message}
              dirty={dirtyFields.train_min_images}
            >
              <Input
                type="number"
                inputMode="numeric"
                min={1}
                max={100}
                step={1}
                {...form.register("train_min_images")}
                disabled={mut.isPending}
              />
            </Field>
            <Field
              label="Max training images"
              error={errors.train_max_images?.message}
              dirty={dirtyFields.train_max_images}
            >
              <Input
                type="number"
                inputMode="numeric"
                min={1}
                max={100}
                step={1}
                {...form.register("train_max_images")}
                disabled={mut.isPending}
              />
            </Field>
          </div>

          <div className="rounded-lg border bg-muted/10 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium">Auto-update embeddings</p>
                <p className="text-xs text-muted-foreground">
                  When a camera recognizes an employee above the threshold
                  below, automatically add the frame as a new training image
                  (rate-limited per employee).
                </p>
              </div>
              <Switch
                checked={autoUpdateEnabled}
                onCheckedChange={(v) =>
                  form.setValue("auto_update_enabled", v, { shouldDirty: true })
                }
                disabled={mut.isPending}
              />
            </div>

            <div
              className={cn(
                "mt-4 grid gap-4 md:grid-cols-2",
                !autoUpdateEnabled && "pointer-events-none opacity-50",
              )}
            >
              <Field
                label="Auto-update threshold"
                hint="Match confidence required to qualify."
                error={errors.auto_update_threshold?.message}
                dirty={dirtyFields.auto_update_threshold}
              >
                <Input
                  type="number"
                  inputMode="decimal"
                  min={0.01}
                  max={0.99}
                  step={0.01}
                  {...form.register("auto_update_threshold")}
                  disabled={mut.isPending || !autoUpdateEnabled}
                />
              </Field>
              <Field
                label="Auto-update cooldown (seconds)"
                hint="Min interval between auto-adds per employee."
                error={errors.auto_update_cooldown_seconds?.message}
                dirty={dirtyFields.auto_update_cooldown_seconds}
              >
                <Input
                  type="number"
                  inputMode="numeric"
                  min={60}
                  max={86400}
                  step={60}
                  {...form.register("auto_update_cooldown_seconds")}
                  disabled={mut.isPending || !autoUpdateEnabled}
                />
              </Field>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <p className="text-xs text-muted-foreground">
          Last updated{" "}
          {(() => {
            try {
              return format(parseISO(initial.updated_at), "PPpp");
            } catch {
              return initial.updated_at;
            }
          })()}
          {initial.updated_by ? ` · by admin #${initial.updated_by}` : ""}
        </p>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={resetToServer}
            disabled={!isDirty || mut.isPending}
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
          <Button type="submit" disabled={!isDirty || mut.isPending}>
            {mut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {mut.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>
    </form>
  );
}

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  dirty?: boolean;
  children: React.ReactNode;
}

function Field({ label, hint, error, dirty, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label>{label}</Label>
        {dirty && (
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-label="modified" />
        )}
      </div>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

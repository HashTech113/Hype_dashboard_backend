"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { format, parseISO } from "date-fns";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { EmployeePicker } from "@/components/training/employee-picker";
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
  useCreateManualEvent,
  useUpdateEvent,
} from "@/lib/hooks/use-attendance";
import { useCameras } from "@/lib/hooks/use-cameras";
import type {
  AttendanceEventDetail,
  EventType,
} from "@/lib/types/attendance";
import type { Employee } from "@/lib/types/employee";
import { cn } from "@/lib/utils";

const schema = z.object({
  event_type: z.enum(["IN", "BREAK_OUT", "BREAK_IN", "OUT"]),
  event_time: z.string().min(1, "Required"),
  camera_id: z.string(),
  note: z.string().max(512).optional(),
});

type Values = z.infer<typeof schema>;

function isoFromLocal(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString();
}

function localFromIso(iso: string): string {
  try {
    return format(parseISO(iso), "yyyy-MM-dd'T'HH:mm");
  } catch {
    return "";
  }
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  event?: AttendanceEventDetail | null;
  presetEmployee?: Employee | null;
}

export function ManualEventDialog({
  open,
  onOpenChange,
  mode,
  event,
  presetEmployee,
}: Props) {
  const isCreate = mode === "create";
  const { data: cameras } = useCameras();
  const createMut = useCreateManualEvent();
  const updateMut = useUpdateEvent();
  const submitting = createMut.isPending || updateMut.isPending;

  const [employee, setEmployee] = useState<Employee | null>(
    presetEmployee ?? null,
  );
  const [employeeError, setEmployeeError] = useState<string | null>(null);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      event_type: "IN",
      event_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
      camera_id: "",
      note: "",
    },
  });

  useEffect(() => {
    if (!open) return;
    setEmployeeError(null);
    if (isCreate) {
      form.reset({
        event_type: "IN",
        event_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
        camera_id: "",
        note: "",
      });
      setEmployee(presetEmployee ?? null);
    } else if (event) {
      form.reset({
        event_type: event.event_type,
        event_time: localFromIso(event.event_time),
        camera_id: event.camera_id ? String(event.camera_id) : "",
        note: event.note ?? "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, event?.id]);

  const errors = form.formState.errors;

  function submit(values: Values) {
    const cameraId =
      values.camera_id && values.camera_id !== "__none"
        ? Number.parseInt(values.camera_id, 10)
        : null;
    const note = values.note && values.note.trim() ? values.note.trim() : null;

    if (isCreate) {
      if (!employee) {
        setEmployeeError("Select an employee first");
        return;
      }
      createMut.mutate(
        {
          employee_id: employee.id,
          event_type: values.event_type as EventType,
          event_time: isoFromLocal(values.event_time),
          camera_id: cameraId,
          note,
        },
        { onSuccess: () => onOpenChange(false) },
      );
    } else if (event) {
      updateMut.mutate(
        {
          eventId: event.id,
          payload: {
            event_type: values.event_type as EventType,
            event_time: isoFromLocal(values.event_time),
            camera_id: cameraId,
            note,
          },
        },
        { onSuccess: () => onOpenChange(false) },
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isCreate ? "Add manual event" : "Edit event"}
          </DialogTitle>
          <DialogDescription>
            {isCreate
              ? "Create an attendance event on behalf of an employee. It will be flagged as manual and the day's rollup will be recomputed."
              : "Edit this event. Any change marks it as manual with your admin ID and recomputes the affected day."}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit(submit)}
          className="space-y-4"
          noValidate
        >
          {isCreate ? (
            <FormField label="Employee" required error={employeeError ?? undefined}>
              <EmployeePicker
                value={employee}
                onChange={(e) => {
                  setEmployee(e);
                  setEmployeeError(null);
                }}
              />
            </FormField>
          ) : (
            <div className="rounded-md border bg-muted/10 px-3 py-2 text-sm">
              <p className="text-xs text-muted-foreground">Employee</p>
              <p className="font-medium">
                {event?.employee_name}{" "}
                <span className="text-muted-foreground">
                  · {event?.employee_code}
                </span>
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Event type" required error={errors.event_type?.message}>
              <Select
                value={form.watch("event_type")}
                onValueChange={(v) =>
                  form.setValue("event_type", v as EventType, {
                    shouldDirty: true,
                  })
                }
                disabled={submitting}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="IN">IN</SelectItem>
                  <SelectItem value="BREAK_OUT">Break out</SelectItem>
                  <SelectItem value="BREAK_IN">Break in</SelectItem>
                  <SelectItem value="OUT">OUT</SelectItem>
                </SelectContent>
              </Select>
            </FormField>

            <FormField
              label="Timestamp"
              required
              error={errors.event_time?.message}
            >
              <Input
                type="datetime-local"
                {...form.register("event_time")}
                disabled={submitting}
              />
            </FormField>

            <FormField
              label="Camera (optional)"
              className="sm:col-span-2"
              hint="Attach a camera if you're recording where this event happened."
            >
              <Select
                value={form.watch("camera_id") || "__none"}
                onValueChange={(v) =>
                  form.setValue("camera_id", v === "__none" ? "" : v, {
                    shouldDirty: true,
                  })
                }
                disabled={submitting}
              >
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">None</SelectItem>
                  {(cameras ?? []).map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name} · {c.camera_type}
                      {c.location ? ` · ${c.location}` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField
              label="Note (optional)"
              className="sm:col-span-2"
              error={errors.note?.message}
              hint="Why this event was added or edited — visible in the audit trail."
            >
              <Textarea
                rows={3}
                maxLength={512}
                {...form.register("note")}
                disabled={submitting}
              />
            </FormField>
          </div>

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
              {isCreate ? "Add event" : "Save changes"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FormField({
  label,
  required,
  error,
  hint,
  className,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label
        className={cn(
          required &&
            "after:ml-0.5 after:text-destructive after:content-['*']",
        )}
      >
        {label}
      </Label>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

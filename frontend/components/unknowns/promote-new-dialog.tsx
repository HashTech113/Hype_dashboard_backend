"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, UserPlus } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { UnknownFaceImage } from "@/components/unknowns/unknown-face-image";
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
import { usePromoteToNewEmployee } from "@/lib/hooks/use-unknowns";
import type { UnknownClusterDetail } from "@/lib/types/unknowns";
import { cn } from "@/lib/utils";

const schema = z.object({
  employee_code: z.string().trim().min(1, "Code is required").max(64),
  name: z.string().trim().min(1, "Name is required").max(128),
  email: z
    .string()
    .trim()
    .max(128)
    .optional()
    .or(z.literal(""))
    .refine(
      (v) => !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v),
      "Invalid email",
    ),
  phone: z.string().trim().max(32).optional().or(z.literal("")),
  designation: z.string().trim().max(128).optional().or(z.literal("")),
  department: z.string().trim().max(128).optional().or(z.literal("")),
  join_date: z.string().optional().or(z.literal("")),
});

type Values = z.infer<typeof schema>;

interface PromoteNewDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  cluster: UnknownClusterDetail | null;
  onPromoted?: () => void;
}

function toUndef(v: string | undefined): string | undefined {
  return v && v.length > 0 ? v : undefined;
}

export function PromoteNewDialog({
  open,
  onOpenChange,
  cluster,
  onPromoted,
}: PromoteNewDialogProps) {
  const promote = usePromoteToNewEmployee();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      employee_code: "",
      name: cluster?.label ?? "",
      email: "",
      phone: "",
      designation: "",
      department: "",
      join_date: "",
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        employee_code: "",
        name: cluster?.label ?? "",
        email: "",
        phone: "",
        designation: "",
        department: "",
        join_date: "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, cluster?.id, cluster?.label]);

  if (!cluster) return null;

  const captureCount = cluster.captures.filter((c) => c.status === "KEEP").length;

  function handleSubmit(values: Values) {
    if (!cluster) return;
    promote.mutate(
      {
        clusterId: cluster.id,
        payload: {
          employee_code: values.employee_code.trim(),
          name: values.name.trim(),
          email: toUndef(values.email),
          phone: toUndef(values.phone),
          designation: toUndef(values.designation),
          department: toUndef(values.department),
          join_date: toUndef(values.join_date),
          is_active: true,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          onPromoted?.();
        },
      },
    );
  }

  const errors = form.formState.errors;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            Add as employee
          </DialogTitle>
          <DialogDescription>
            Enrol this person as a new employee. Their {captureCount} captured
            face image{captureCount === 1 ? "" : "s"} will be used for training
            — the recognizer will identify them on the next frame.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-4">
          <UnknownFaceImage
            captureId={cluster.representative_capture_id}
            className="h-28 w-28 shrink-0 rounded-md"
            alt="Cluster representative"
          />
          <div className="flex-1 text-xs text-muted-foreground">
            <p>
              <span className="font-medium text-foreground">Cluster #{cluster.id}</span>
              {cluster.label ? ` ("${cluster.label}")` : ""}
            </p>
            <p className="mt-1">
              {captureCount} quality face image{captureCount === 1 ? "" : "s"}{" "}
              ready to enrol — the highest-quality ones will be used (up to the
              per-employee training cap).
            </p>
            <p className="mt-1 text-[11px]">
              Embeddings are reused verbatim from capture time — no re-detection,
              no precision loss.
            </p>
          </div>
        </div>

        <form
          onSubmit={form.handleSubmit(handleSubmit)}
          className="space-y-4"
          noValidate
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Employee code" required error={errors.employee_code?.message}>
              <Input
                placeholder="EMP-042"
                autoFocus
                {...form.register("employee_code")}
                disabled={promote.isPending}
              />
            </Field>
            <Field label="Full name" required error={errors.name?.message}>
              <Input
                placeholder="Jane Doe"
                {...form.register("name")}
                disabled={promote.isPending}
              />
            </Field>
            <Field label="Email" error={errors.email?.message}>
              <Input
                type="email"
                placeholder="jane@example.com"
                {...form.register("email")}
                disabled={promote.isPending}
              />
            </Field>
            <Field label="Phone">
              <Input
                placeholder="+91 98765 43210"
                {...form.register("phone")}
                disabled={promote.isPending}
              />
            </Field>
            <Field label="Designation">
              <Input
                placeholder="Senior Engineer"
                {...form.register("designation")}
                disabled={promote.isPending}
              />
            </Field>
            <Field label="Department">
              <Input
                placeholder="Engineering"
                {...form.register("department")}
                disabled={promote.isPending}
              />
            </Field>
            <Field label="Join date">
              <Input
                type="date"
                {...form.register("join_date")}
                disabled={promote.isPending}
              />
            </Field>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={promote.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={promote.isPending}>
              {promote.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Add as employee &amp; train
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

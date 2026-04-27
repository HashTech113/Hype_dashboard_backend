"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Employee, EmployeeCreate, EmployeeUpdate } from "@/lib/types/employee";
import { cn } from "@/lib/utils";

const baseFields = {
  name: z.string().trim().min(1, "Name is required").max(128),
  email: z
    .string()
    .trim()
    .max(128)
    .optional()
    .or(z.literal(""))
    .transform((v) => (v ? v : undefined))
    .refine(
      (v) => v === undefined || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v),
      "Invalid email",
    ),
  phone: z.string().trim().max(32).optional().or(z.literal("")),
  designation: z.string().trim().max(128).optional().or(z.literal("")),
  department: z.string().trim().max(128).optional().or(z.literal("")),
  join_date: z.string().optional().or(z.literal("")),
} as const;

const createSchema = z.object({
  employee_code: z.string().trim().min(1, "Code is required").max(64),
  ...baseFields,
  is_active: z.boolean().default(true),
});

const editSchema = z.object({
  ...baseFields,
  is_active: z.boolean(),
});

type CreateValues = z.infer<typeof createSchema>;
type EditValues = z.infer<typeof editSchema>;

interface BaseProps {
  submitting: boolean;
  onCancel: () => void;
}

interface CreateProps extends BaseProps {
  mode: "create";
  onSubmit: (values: EmployeeCreate) => void;
  initial?: undefined;
}
interface EditProps extends BaseProps {
  mode: "edit";
  onSubmit: (values: EmployeeUpdate) => void;
  initial: Employee;
}

type Props = CreateProps | EditProps;

function toUndef(v: string | undefined | null): string | undefined {
  return v && v.length > 0 ? v : undefined;
}

export function EmployeeForm(props: Props) {
  const isCreate = props.mode === "create";

  const form = useForm<CreateValues | EditValues>({
    resolver: zodResolver(isCreate ? createSchema : editSchema) as never,
    defaultValues: isCreate
      ? {
          employee_code: "",
          name: "",
          email: "",
          phone: "",
          designation: "",
          department: "",
          join_date: "",
          is_active: true,
        }
      : {
          name: props.initial.name,
          email: props.initial.email ?? "",
          phone: props.initial.phone ?? "",
          designation: props.initial.designation ?? "",
          department: props.initial.department ?? "",
          join_date: props.initial.join_date ?? "",
          is_active: props.initial.is_active,
        },
  });

  useEffect(() => {
    if (!isCreate) {
      form.reset({
        name: props.initial.name,
        email: props.initial.email ?? "",
        phone: props.initial.phone ?? "",
        designation: props.initial.designation ?? "",
        department: props.initial.department ?? "",
        join_date: props.initial.join_date ?? "",
        is_active: props.initial.is_active,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCreate ? null : props.initial.id]);

  const errors = form.formState.errors;

  function handleSubmit(values: CreateValues | EditValues) {
    const payload = {
      name: values.name,
      email: toUndef(values.email as string | undefined),
      phone: toUndef(values.phone as string | undefined),
      designation: toUndef(values.designation as string | undefined),
      department: toUndef(values.department as string | undefined),
      join_date: toUndef(values.join_date as string | undefined),
      is_active: values.is_active,
    };
    if (isCreate) {
      (props.onSubmit as (v: EmployeeCreate) => void)({
        employee_code: (values as CreateValues).employee_code.trim(),
        ...payload,
      });
    } else {
      (props.onSubmit as (v: EmployeeUpdate) => void)(payload);
    }
  }

  return (
    <form
      onSubmit={form.handleSubmit(handleSubmit)}
      className="space-y-4"
      noValidate
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {isCreate && (
          <Field
            label="Employee code"
            required
            error={
              (errors as typeof errors & { employee_code?: { message?: string } })
                .employee_code?.message
            }
          >
            <Input
              placeholder="EMP-001"
              {...form.register("employee_code" as never)}
              disabled={props.submitting}
            />
          </Field>
        )}
        <Field label="Name" required error={errors.name?.message}>
          <Input
            placeholder="Asha Kumar"
            {...form.register("name")}
            disabled={props.submitting}
          />
        </Field>
        <Field label="Email" error={errors.email?.message}>
          <Input
            type="email"
            placeholder="asha@example.com"
            {...form.register("email")}
            disabled={props.submitting}
          />
        </Field>
        <Field label="Phone">
          <Input
            placeholder="+91 98765 43210"
            {...form.register("phone")}
            disabled={props.submitting}
          />
        </Field>
        <Field label="Role / Designation">
          <Input
            placeholder="Senior Engineer"
            {...form.register("designation")}
            disabled={props.submitting}
          />
        </Field>
        <Field label="Department">
          <Input
            placeholder="Engineering"
            {...form.register("department")}
            disabled={props.submitting}
          />
        </Field>
        <Field label="Join date">
          <Input
            type="date"
            {...form.register("join_date")}
            disabled={props.submitting}
          />
        </Field>
        <Field label="Status">
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input accent-primary"
              {...form.register("is_active")}
              disabled={props.submitting}
            />
            Active
          </label>
        </Field>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={props.onCancel}
          disabled={props.submitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={props.submitting}>
          {props.submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {isCreate ? "Create employee" : "Save changes"}
        </Button>
      </div>
    </form>
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
      <Label className={cn(required && "after:ml-0.5 after:text-destructive after:content-['*']")}>
        {label}
      </Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

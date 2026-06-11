"use client";

/**
 * Voluntary password-change page.
 *
 * Linked from the topbar menu. No automatic redirect — the operator
 * comes here when they want to rotate.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Eye, EyeOff, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { authApi } from "@/lib/api/auth";
import { useAuth } from "@/lib/auth/context";
import { cn } from "@/lib/utils";

const schema = z
  .object({
    current_password: z.string().min(1, "Current password is required"),
    new_password: z.string().min(8, "New password must be at least 8 characters"),
    confirm_password: z.string().min(1, "Confirm your new password"),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  })
  .refine((v) => v.new_password !== v.current_password, {
    message: "New password must differ from current",
    path: ["new_password"],
  });

type Values = z.infer<typeof schema>;

export default function ChangePasswordPage() {
  const { admin, refresh } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  });

  async function onSubmit(values: Values) {
    setSubmitting(true);
    try {
      await authApi.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      setSuccess(true);
      toast.success("Password changed — redirecting...");
      // Refresh the admin profile so must_change_password updates in
      // the context, then hard-navigate so the auth middleware re-checks.
      await refresh();
      setTimeout(() => {
        window.location.assign("/dashboard");
      }, 800);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Could not change password. Please try again.";
      toast.error(msg);
      if (err instanceof ApiError && err.message.toLowerCase().includes("current")) {
        form.setError("current_password", { message: msg });
      } else {
        form.setError("new_password", { message: msg });
      }
    } finally {
      setSubmitting(false);
    }
  }

  const errors = form.formState.errors;

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 p-4">
      <Card className="p-6">
        <h1 className="mb-1 text-xl font-semibold">Change password</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          Account: <span className="font-mono">{admin?.username ?? "..."}</span>
        </p>

        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-4"
          noValidate
        >
          <PasswordField
            label="Current password"
            register={form.register("current_password")}
            show={showCurrent}
            toggle={() => setShowCurrent((v) => !v)}
            error={errors.current_password?.message}
            disabled={submitting || success}
            autoComplete="current-password"
          />
          <PasswordField
            label="New password"
            register={form.register("new_password")}
            show={showNew}
            toggle={() => setShowNew((v) => !v)}
            error={errors.new_password?.message}
            disabled={submitting || success}
            autoComplete="new-password"
            hint="At least 8 characters. Use a mix of upper/lower/digits/symbols."
          />
          <PasswordField
            label="Confirm new password"
            register={form.register("confirm_password")}
            show={showNew}
            toggle={() => setShowNew((v) => !v)}
            error={errors.confirm_password?.message}
            disabled={submitting || success}
            autoComplete="new-password"
          />

          <Button
            type="submit"
            className="w-full"
            disabled={submitting || success}
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {success && <CheckCircle2 className="h-4 w-4" />}
            {success
              ? "Password changed"
              : submitting
                ? "Changing..."
                : "Change password"}
          </Button>
        </form>
      </Card>
    </div>
  );
}

function PasswordField({
  label,
  register,
  show,
  toggle,
  error,
  disabled,
  autoComplete,
  hint,
}: {
  label: string;
  register: ReturnType<ReturnType<typeof useForm<Values>>["register"]>;
  show: boolean;
  toggle: () => void;
  error?: string;
  disabled?: boolean;
  autoComplete?: string;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="relative">
        <Input
          type={show ? "text" : "password"}
          autoComplete={autoComplete}
          className={cn("pr-10", error && "border-destructive")}
          {...register}
          disabled={disabled}
        />
        <button
          type="button"
          onClick={toggle}
          tabIndex={-1}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {hint && !error && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

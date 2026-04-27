"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { cn } from "@/lib/utils";

const schema = z.object({
  username: z
    .string()
    .min(1, "Username is required")
    .max(64, "Username is too long"),
  password: z
    .string()
    .min(1, "Password is required")
    .max(256, "Password is too long"),
});

type LoginValues = z.infer<typeof schema>;

export function LoginForm() {
  const searchParams = useSearchParams();
  const rawNext = searchParams.get("next");
  const nextPath = !rawNext || rawNext === "/" ? "/dashboard" : rawNext;
  const { login } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const form = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });

  const errors = form.formState.errors;

  async function onSubmit(values: LoginValues) {
    setSubmitting(true);
    try {
      await login(values.username.trim(), values.password);
      toast.success("Welcome back");
      // Hard navigation: ensures the freshly-set token cookie is on the
      // request, the middleware sees it, and AuthProvider remounts with
      // the cookie present (skipping any React state-timing races between
      // setAdmin() and router.replace() that can cause the dashboard layout
      // to bounce back to /login).
      window.location.assign(nextPath);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Unable to sign in. Try again.";
      toast.error(msg);
      form.setError("password", { message: "" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={form.handleSubmit(onSubmit)}
      className="space-y-4"
      noValidate
    >
      <div className="space-y-2">
        <Label htmlFor="username">Username or email</Label>
        <Input
          id="username"
          type="text"
          autoComplete="username"
          autoFocus
          spellCheck={false}
          inputMode="email"
          className={cn(errors.username && "border-destructive")}
          {...form.register("username")}
          disabled={submitting}
          aria-invalid={!!errors.username}
          aria-describedby={errors.username ? "username-error" : undefined}
        />
        {errors.username && (
          <p id="username-error" className="text-xs text-destructive">
            {errors.username.message}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <div className="relative">
          <Input
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            className={cn("pr-10", errors.password && "border-destructive")}
            {...form.register("password")}
            disabled={submitting}
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? "password-error" : undefined}
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            tabIndex={-1}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {showPassword ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </button>
        </div>
        {errors.password?.message && (
          <p id="password-error" className="text-xs text-destructive">
            {errors.password.message}
          </p>
        )}
      </div>

      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
        {submitting ? "Signing in..." : "Sign in"}
      </Button>

      <p className="pt-2 text-center text-xs text-muted-foreground">
        Admin access only &middot; contact your super-admin for credentials
      </p>
    </form>
  );
}

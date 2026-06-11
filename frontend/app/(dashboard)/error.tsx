"use client";

/**
 * Dashboard route-group error boundary (P0.11).
 *
 * Catches errors inside any /dashboard, /cameras, /attendance, etc. page.
 * The root layout (topbar, sidebar) stays intact — only the page area
 * shows the error. The operator can navigate away to a different page or
 * click Reset to retry the current one.
 */

import { AlertTriangle, RefreshCw } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[dashboard-error] caught:", error, "digest:", error.digest);
  }, [error]);

  // Extract API context if this is an ApiError (carries status + code)
  const apiError = error as Error & {
    status?: number;
    code?: string;
  };
  const isApiError = typeof apiError.status === "number";

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
        <div className="mb-3 flex justify-center">
          <AlertTriangle className="h-10 w-10 text-destructive" />
        </div>
        <h2 className="mb-2 text-lg font-semibold">
          {isApiError && apiError.status === 503
            ? "The backend is temporarily unavailable"
            : isApiError && (apiError.status ?? 0) >= 500
              ? "The server hit an error"
              : "Something went wrong on this page"}
        </h2>
        <p className="mb-4 text-sm text-muted-foreground">
          {error.message || "An unexpected error occurred. Please try again."}
        </p>
        {error.digest && (
          <p className="mb-4 font-mono text-[11px] text-muted-foreground">
            Error ID: {error.digest}
          </p>
        )}
        <div className="flex justify-center gap-2">
          <Button onClick={() => reset()} size="sm">
            <RefreshCw className="mr-1 h-4 w-4" />
            Try again
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => (window.location.href = "/dashboard")}
          >
            Back to dashboard
          </Button>
        </div>
      </div>
    </div>
  );
}

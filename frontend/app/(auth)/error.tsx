"use client";

/**
 * /login error boundary. Keeps the operator unstuck if the login form
 * itself throws.
 */

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function AuthError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[auth-error] caught:", error, "digest:", error.digest);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
        <div className="mb-3 flex justify-center">
          <AlertTriangle className="h-10 w-10 text-destructive" />
        </div>
        <h2 className="mb-2 text-lg font-semibold">Sign-in is unavailable</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          {error.message || "Could not load the login page."}
        </p>
        <Button onClick={() => reset()} size="sm">
          Try again
        </Button>
      </div>
    </div>
  );
}

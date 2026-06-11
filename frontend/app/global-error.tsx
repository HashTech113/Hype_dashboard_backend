"use client";

/**
 * Last-resort error boundary (P0.11).
 *
 * Catches errors above the root layout — render failures during providers
 * setup, hydration mismatches, etc. Next.js requires this file to render
 * its own <html>/<body> because the root layout itself is the thing that
 * failed.
 *
 * Audit context: without this, any uncaught render error white-screens
 * the entire admin panel. With it, the operator sees a recoverable
 * "Something went wrong" page with a Reset button.
 */

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface in the browser console for the operator + any error-tracking
    // tool we add later. We deliberately do NOT log to backend here — the
    // network may itself be the cause of the error.
    // eslint-disable-next-line no-console
    console.error("[global-error] caught:", error, "digest:", error.digest);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
          background: "#0a0a0a",
          color: "#f5f5f5",
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
        }}
      >
        <div
          style={{
            maxWidth: 480,
            background: "#171717",
            border: "1px solid #404040",
            borderRadius: 12,
            padding: 32,
            textAlign: "center",
          }}
        >
          <h1 style={{ margin: "0 0 12px", fontSize: 24 }}>
            Something went wrong
          </h1>
          <p style={{ margin: "0 0 24px", color: "#a3a3a3", fontSize: 14 }}>
            The admin panel encountered an unexpected error. You can try to
            reload — if it keeps happening, check the backend is running and
            then contact support.
          </p>
          {error.digest && (
            <p
              style={{
                margin: "0 0 24px",
                color: "#737373",
                fontSize: 12,
                fontFamily: "ui-monospace, monospace",
              }}
            >
              Error ID: {error.digest}
            </p>
          )}
          <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
            <button
              onClick={() => reset()}
              style={{
                padding: "10px 20px",
                background: "#2563eb",
                color: "white",
                border: "none",
                borderRadius: 6,
                fontSize: 14,
                cursor: "pointer",
                fontWeight: 500,
              }}
            >
              Try again
            </button>
            <button
              onClick={() => (window.location.href = "/dashboard")}
              style={{
                padding: "10px 20px",
                background: "transparent",
                color: "#f5f5f5",
                border: "1px solid #404040",
                borderRadius: 6,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              Go to dashboard
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}

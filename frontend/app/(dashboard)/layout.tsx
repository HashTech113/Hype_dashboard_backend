"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/context";
import { clearToken } from "@/lib/auth/session";

const STUCK_AFTER_SECONDS = 6;

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { admin, loading } = useAuth();
  const router = useRouter();
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    if (!loading && !admin) {
      router.replace("/login");
    }
  }, [admin, loading, router]);

  // Visible escape-hatch if the session refresh hangs for more than a few
  // seconds. The most common cause is a stale JS bundle in the browser cache
  // pointing at the wrong backend, or a hydration mismatch — both of which
  // would otherwise leave the operator staring at a spinner forever.
  useEffect(() => {
    if (!loading) {
      setStuck(false);
      return;
    }
    const t = setTimeout(() => setStuck(true), STUCK_AFTER_SECONDS * 1000);
    return () => clearTimeout(t);
  }, [loading]);

  if (loading && !stuck) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background p-8 text-sm text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p>Loading your session…</p>
      </div>
    );
  }

  if (loading && stuck) {
    // Hangs after this long are almost always a cached old JS bundle or a
    // missing/expired auth cookie. Surface enough info that the operator can
    // recover without DevTools spelunking.
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "(NEXT_PUBLIC_API_URL not set)";
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8 text-sm">
        <AlertCircle className="h-8 w-8 text-amber-500" />
        <p className="text-base font-semibold">Sign-in is taking longer than usual</p>
        <div className="max-w-md space-y-2 text-center text-muted-foreground">
          <p>
            The page is waiting for the backend at{" "}
            <code className="rounded bg-muted px-1 text-xs">{apiUrl}</code>.
          </p>
          <p>
            This usually means your browser cached an older version of the app.
            Try one of these in order:
          </p>
          <ol className="text-left list-decimal pl-6 space-y-1">
            <li>Hard reload: <kbd className="rounded bg-muted px-1 text-xs">Ctrl + Shift + R</kbd></li>
            <li>If that doesn&apos;t work, click <em>Sign out</em> below and log in again</li>
            <li>If that still fails, the backend may be down — check <code className="rounded bg-muted px-1 text-xs">{apiUrl.replace(/\/api\/v1$/, "")}/health</code></li>
          </ol>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => window.location.reload()}>Hard reload</Button>
          <Button
            variant="outline"
            onClick={() => {
              clearToken();
              window.location.assign("/login");
            }}
          >
            Sign out
          </Button>
        </div>
      </div>
    );
  }

  if (!admin) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background p-8 text-sm text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p>Redirecting to sign in…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

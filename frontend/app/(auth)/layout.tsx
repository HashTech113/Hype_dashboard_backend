import { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-background via-background to-muted/40 p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(56,189,248,0.08),transparent_50%),radial-gradient(ellipse_at_bottom,rgba(168,85,247,0.08),transparent_50%)]" />
      <div className="relative z-10 w-full max-w-md">{children}</div>
    </div>
  );
}

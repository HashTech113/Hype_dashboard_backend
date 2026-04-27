import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function LoginPage() {
  return (
    <Card className="border-border/60 shadow-xl backdrop-blur">
      <CardHeader className="space-y-2 text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-6 w-6"
          >
            <rect width="20" height="14" x="2" y="5" rx="2" />
            <path d="M7 14a4 4 0 0 1 8 0" />
            <circle cx="11" cy="10" r="2" />
          </svg>
        </div>
        <CardTitle className="text-2xl">Sign in</CardTitle>
        <CardDescription>
          AI CCTV Attendance &mdash; admin access only
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Suspense is required by Next 15 because LoginForm calls
            useSearchParams() to read the `?next=` param. */}
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </CardContent>
    </Card>
  );
}

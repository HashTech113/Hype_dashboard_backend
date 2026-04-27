import { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: number | string | null | undefined;
  icon?: LucideIcon;
  hint?: string;
  tone?: "default" | "success" | "warning" | "destructive" | "primary";
  loading?: boolean;
  className?: string;
}

const ICON_TONES: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "bg-muted text-muted-foreground",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  destructive: "bg-destructive/15 text-destructive",
  primary: "bg-primary/15 text-primary",
};

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
  loading,
  className,
}: StatCardProps) {
  return (
    <Card
      className={cn(
        "overflow-hidden transition-shadow duration-200 hover:shadow-md",
        className,
      )}
    >
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            {loading ? (
              <Skeleton className="mt-2 h-8 w-20" />
            ) : (
              <p className="mt-1.5 text-3xl font-semibold tabular-nums leading-none">
                {value ?? "—"}
              </p>
            )}
            {hint && (
              <p className="mt-2 truncate text-xs text-muted-foreground">
                {hint}
              </p>
            )}
          </div>
          {Icon && (
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                ICON_TONES[tone],
              )}
            >
              <Icon className="h-5 w-5" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

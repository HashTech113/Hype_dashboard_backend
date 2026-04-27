import { AlertCircle, CheckCircle2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { TrainingResult } from "@/lib/types/training";

interface Props {
  result: TrainingResult | null | undefined;
}

export function TrainingResultPanel({ result }: Props) {
  if (!result) return null;

  const hasAccepted = result.accepted > 0;
  const hasRejected = result.rejected > 0;

  return (
    <div
      className={cn(
        "rounded-md border p-4",
        hasAccepted
          ? "border-success/40 bg-success/5"
          : hasRejected
            ? "border-destructive/40 bg-destructive/5"
            : "border-border bg-muted/20",
      )}
    >
      <div className="flex items-start gap-3">
        {hasAccepted ? (
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
        ) : (
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            {hasAccepted ? "Last enrollment" : "Nothing was enrolled"}
          </p>
          <div className="mt-2 grid grid-cols-3 gap-3 text-xs">
            <Stat label="Accepted" value={result.accepted} tone="success" />
            <Stat
              label="Rejected"
              value={result.rejected}
              tone={hasRejected ? "destructive" : "muted"}
            />
            <Stat
              label="Total embeddings"
              value={result.total_embeddings}
              tone="primary"
            />
          </div>
          {result.errors.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                {result.errors.length} issue{result.errors.length === 1 ? "" : "s"} — show details
              </summary>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {result.errors.map((err, i) => (
                  <li key={i} className="rounded bg-muted/40 px-2 py-1">
                    {err}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "destructive" | "muted" | "primary";
}) {
  const toneClass = {
    success: "text-success",
    destructive: "text-destructive",
    muted: "text-muted-foreground",
    primary: "text-primary",
  }[tone];
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className={cn("mt-0.5 text-lg font-semibold tabular-nums", toneClass)}>
        {value}
      </p>
    </div>
  );
}

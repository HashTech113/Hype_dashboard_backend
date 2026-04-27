"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

interface PaginationBarProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
  loading?: boolean;
}

export function PaginationBar({
  total,
  limit,
  offset,
  onChange,
  loading,
}: PaginationBarProps) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(total, offset + limit);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between gap-4 border-t px-4 py-3 text-sm">
      <p className="text-muted-foreground tabular-nums">
        {loading ? (
          <span>Loading…</span>
        ) : total === 0 ? (
          "0 results"
        ) : (
          <>
            Showing <span className="font-medium text-foreground">{start}</span>{" "}
            – <span className="font-medium text-foreground">{end}</span> of{" "}
            <span className="font-medium text-foreground">{total}</span>
          </>
        )}
      </p>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onChange(Math.max(0, offset - limit))}
          disabled={!canPrev || loading}
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onChange(offset + limit)}
          disabled={!canNext || loading}
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

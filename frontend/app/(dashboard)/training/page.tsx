"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { TrainingConsole } from "@/components/training/training-console";
import { useEmployee } from "@/lib/hooks/use-employees";

function TrainingContent() {
  const searchParams = useSearchParams();
  const raw = searchParams.get("employee");
  const preselectId = raw ? Number.parseInt(raw, 10) : null;
  const validId =
    preselectId !== null && Number.isFinite(preselectId) && preselectId > 0
      ? preselectId
      : null;

  const { data: preselected, isLoading } = useEmployee(validId);

  if (validId !== null && isLoading) {
    return <p className="text-sm text-muted-foreground">Loading employee…</p>;
  }
  return <TrainingConsole initialEmployee={preselected ?? null} />;
}

export default function TrainingPage() {
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <PageHeader
        title="Face training"
        description="Enroll face images for recognition. More variety (angles, lighting) produces better accuracy."
      />
      {/* Suspense satisfies Next 15's static-generation rule for
          useSearchParams (it's used inside TrainingContent). */}
      <Suspense
        fallback={
          <p className="text-sm text-muted-foreground">Loading…</p>
        }
      >
        <TrainingContent />
      </Suspense>
    </div>
  );
}

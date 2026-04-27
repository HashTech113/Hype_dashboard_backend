"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { SettingsForm } from "@/components/settings/settings-form";
import { Card, CardContent } from "@/components/ui/card";
import { useSettings } from "@/lib/hooks/use-settings";

export default function SettingsPage() {
  const { data, isLoading, isError, error } = useSettings();

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Runtime-tunable configuration. Changes take effect immediately — no restart needed."
      />

      {isLoading ? (
        <Card>
          <CardContent className="flex items-center gap-2 p-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading current settings…
          </CardContent>
        </Card>
      ) : isError || !data ? (
        <Card>
          <CardContent className="flex items-center gap-2 p-8 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            {error instanceof Error
              ? error.message
              : "Could not load settings."}
          </CardContent>
        </Card>
      ) : (
        <SettingsForm initial={data} />
      )}
    </div>
  );
}

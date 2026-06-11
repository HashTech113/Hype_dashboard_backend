"use client";

import { Plus, Radar, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { CameraFormDialog } from "@/components/cameras/camera-form-dialog";
import { CameraTable } from "@/components/cameras/camera-table";
import { CameraWizardDialog } from "@/components/cameras/camera-wizard-dialog";
import { DeleteCameraDialog } from "@/components/cameras/delete-camera-dialog";
import { DetectCamerasDialog } from "@/components/cameras/detect-cameras-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCameras, useCamerasHealth } from "@/lib/hooks/use-cameras";
import type { Camera } from "@/lib/types/camera";

export default function CamerasPage() {
  const { data: cameras, isLoading } = useCameras();
  const { data: health } = useCamerasHealth(5_000);

  const [formOpen, setFormOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [detectOpen, setDetectOpen] = useState(false);
  const [prefillIp, setPrefillIp] = useState<string | null>(null);
  const [editing, setEditing] = useState<Camera | null>(null);
  const [deleting, setDeleting] = useState<Camera | null>(null);

  const summary = useMemo(() => {
    const list = cameras ?? [];
    const entry = list.filter((c) => c.camera_type === "ENTRY").length;
    const exit = list.filter((c) => c.camera_type === "EXIT").length;
    const active = list.filter((c) => c.is_active).length;
    // A worker counts as "live" only when it has actually received a recent
    // frame — the heartbeat keeps ticking even while RTSP reads fail.
    const running = (health ?? []).filter(
      (h) =>
        h.is_running &&
        !h.last_error &&
        h.last_frame_age_seconds !== null &&
        h.last_frame_age_seconds < 15,
    ).length;
    return { total: list.length, active, running, entry, exit };
  }, [cameras, health]);

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <PageHeader
        title="Cameras"
        description="Connect your IP cameras (Hikvision, Dahua, CP Plus, Axis, Reolink, and most ONVIF brands). Each camera streams live, detects faces, and logs every entry and exit."
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setDetectOpen(true)}
              title="Scan the network for cameras"
            >
              <Radar className="h-4 w-4" />
              Detect on LAN
            </Button>
            <Button onClick={() => setWizardOpen(true)}>
              <Sparkles className="h-4 w-4" />
              Smart Connect
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Plus className="h-4 w-4" />
              Add manually
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryStat label="Total" value={summary.total} />
        <SummaryStat
          label="Active"
          value={`${summary.active}/${summary.total}`}
        />
        <SummaryStat
          label="Live workers"
          value={summary.running}
          tone={
            summary.active > 0 && summary.running < summary.active
              ? "warning"
              : "success"
          }
        />
        <SummaryStat
          label="ENTRY / EXIT"
          value={`${summary.entry} / ${summary.exit}`}
        />
      </div>

      <Card>
        <CameraTable
          cameras={cameras}
          health={health}
          loading={isLoading}
          onEdit={(c) => {
            setEditing(c);
            setFormOpen(true);
          }}
          onDelete={(c) => setDeleting(c)}
        />
      </Card>

      <CameraFormDialog
        open={formOpen}
        onOpenChange={(v) => {
          setFormOpen(v);
          if (!v) setEditing(null);
        }}
        camera={editing}
      />
      <CameraWizardDialog
        open={wizardOpen}
        onOpenChange={(v) => {
          setWizardOpen(v);
          if (!v) setPrefillIp(null);
        }}
        prefillHost={prefillIp ?? undefined}
      />
      <DetectCamerasDialog
        open={detectOpen}
        onOpenChange={setDetectOpen}
        onConnectClick={(cam) => {
          setPrefillIp(cam.ip);
          setWizardOpen(true);
        }}
      />
      <DeleteCameraDialog
        open={deleting !== null}
        onOpenChange={(v) => !v && setDeleting(null)}
        camera={deleting}
      />
    </div>
  );
}

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "warning" | "success";
}) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {tone && (
        <Badge
          variant={tone === "success" ? "success" : "warning"}
          className="mt-2"
        >
          {tone === "success" ? "All healthy" : "Some down"}
        </Badge>
      )}
    </Card>
  );
}

"use client";

import { Loader2, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeleteCamera } from "@/lib/hooks/use-cameras";
import type { Camera } from "@/lib/types/camera";

interface DeleteCameraDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  camera: Camera | null;
}

export function DeleteCameraDialog({
  open,
  onOpenChange,
  camera,
}: DeleteCameraDialogProps) {
  const remove = useDeleteCamera();

  if (!camera) return null;

  function handleConfirm() {
    if (!camera) return;
    remove.mutate(camera.id, {
      onSuccess: () => onOpenChange(false),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PowerOff className="h-5 w-5 text-destructive" />
            Remove camera?
          </DialogTitle>
          <DialogDescription>
            <span className="font-medium text-foreground">{camera.name}</span>{" "}
            will be deactivated and its worker will stop. Past attendance events
            and snapshots are kept. You can re-enable the camera later by
            editing it.
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2 pt-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={remove.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={remove.isPending}
          >
            {remove.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Remove
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

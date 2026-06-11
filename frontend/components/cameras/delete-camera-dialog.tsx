"use client";

import { Loader2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  const [confirmName, setConfirmName] = useState("");

  // Reset the typed name whenever the dialog opens / camera switches.
  useEffect(() => {
    if (open) setConfirmName("");
  }, [open, camera?.id]);

  if (!camera) return null;

  // Case-insensitive comparison — case-sensitivity is operator-hostile
  // ("Office Cam 1" vs "office cam 1") and adds no safety. The typed
  // string-match remains the friction that protects against accidental
  // deletion; the case rules just frustrated users who naturally type
  // in lowercase.
  const canDelete =
    confirmName.trim().toLowerCase() === camera.name.trim().toLowerCase();

  function handleConfirm() {
    if (!camera || !canDelete) return;
    remove.mutate(camera.id, {
      onSuccess: () => onOpenChange(false),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <Trash2 className="h-5 w-5" />
            Delete this camera permanently?
          </DialogTitle>
          <DialogDescription className="space-y-2">
            <span>
              <span className="font-semibold text-foreground">
                {camera.name}
              </span>{" "}
              will be removed from the system. The live stream will stop and
              the camera will disappear from every dashboard view.
            </span>
            <span className="block rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              <strong>Past activity is preserved.</strong> Attendance events,
              snapshots, and unknown-face records that came from this camera
              stay in the database — only the live camera connection goes
              away. You can also re-add the same RTSP URL later as a new
              camera.
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 pt-2">
          <Label htmlFor="confirm-name" className="text-sm">
            Type{" "}
            <span className="font-mono font-semibold">{camera.name}</span> to
            confirm{" "}
            <span className="text-xs font-normal text-muted-foreground">
              (case doesn&apos;t matter)
            </span>
            :
          </Label>
          <Input
            id="confirm-name"
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder={camera.name}
            autoComplete="off"
            disabled={remove.isPending}
          />
        </div>

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
            disabled={remove.isPending || !canDelete}
          >
            {remove.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            <Trash2 className="h-4 w-4" />
            Delete forever
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

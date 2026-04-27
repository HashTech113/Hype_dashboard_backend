"use client";

import { format, formatDistanceToNow } from "date-fns";
import {
  Camera,
  Loader2,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { EmployeePicker } from "@/components/training/employee-picker";
import { UnknownFaceImage } from "@/components/unknowns/unknown-face-image";
import { Badge } from "@/components/ui/badge";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDiscardCluster,
  usePromoteToExistingEmployee,
  useSetClusterLabel,
  useUnknownCluster,
} from "@/lib/hooks/use-unknowns";
import type { Employee } from "@/lib/types/employee";
import type { UnknownClusterDetail } from "@/lib/types/unknowns";
import { cn } from "@/lib/utils";

interface ClusterDetailDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  clusterId: number | null;
  onPromoteNew: (cluster: UnknownClusterDetail) => void;
}

const STATUS_TONE = {
  PENDING: "warning",
  PROMOTED: "success",
  IGNORED: "secondary",
  MERGED: "outline",
} as const;

export function ClusterDetailDialog({
  open,
  onOpenChange,
  clusterId,
  onPromoteNew,
}: ClusterDetailDialogProps) {
  const { data: cluster, isLoading } = useUnknownCluster(open ? clusterId : null);

  const setLabel = useSetClusterLabel();
  const discard = useDiscardCluster();
  const promoteExisting = usePromoteToExistingEmployee();

  const [labelDraft, setLabelDraft] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickedEmployee, setPickedEmployee] = useState<Employee | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  useEffect(() => {
    if (open) {
      setLabelDraft(cluster?.label ?? "");
      setPickedEmployee(null);
      setConfirmDiscard(false);
    }
  }, [open, cluster?.id, cluster?.label]);

  function handleSaveLabel() {
    if (!cluster) return;
    const trimmed = labelDraft.trim();
    setLabel.mutate({ id: cluster.id, label: trimmed === "" ? null : trimmed });
  }

  function handleDiscard() {
    if (!cluster) return;
    discard.mutate(cluster.id, {
      onSuccess: () => onOpenChange(false),
    });
  }

  function handlePromoteExisting(employee: Employee) {
    if (!cluster) return;
    promoteExisting.mutate(
      { clusterId: cluster.id, employeeId: employee.id },
      {
        onSuccess: () => {
          setPickerOpen(false);
          setPickedEmployee(null);
          onOpenChange(false);
        },
      },
    );
  }

  const captures = cluster?.captures ?? [];
  const keepCaptures = captures.filter((c) => c.status === "KEEP");
  const isPending = cluster?.status === "PENDING";

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              {cluster?.label ? cluster.label : (
                <span>Unknown person #{clusterId}</span>
              )}
              {cluster && (
                <Badge variant={STATUS_TONE[cluster.status]}>
                  {cluster.status}
                </Badge>
              )}
            </DialogTitle>
            <DialogDescription>
              Every captured face below is the same unique person. Add them as an
              employee, or discard if they shouldn&apos;t be tracked.
            </DialogDescription>
          </DialogHeader>

          {isLoading || !cluster ? (
            <div className="space-y-4">
              <Skeleton className="h-20 w-full" />
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="aspect-square w-full" />
                ))}
              </div>
            </div>
          ) : (
            <>
              {/* Meta panel */}
              <div className="grid grid-cols-2 gap-3 rounded-md border bg-muted/30 p-3 text-xs sm:grid-cols-4">
                <Meta
                  label="First seen"
                  value={formatDistanceToNow(new Date(cluster.first_seen_at), { addSuffix: true })}
                  hint={format(new Date(cluster.first_seen_at), "PPpp")}
                />
                <Meta
                  label="Last seen"
                  value={formatDistanceToNow(new Date(cluster.last_seen_at), { addSuffix: true })}
                  hint={format(new Date(cluster.last_seen_at), "PPpp")}
                />
                <Meta label="Total faces" value={`${cluster.member_count}`} />
                <Meta
                  label="Captures shown"
                  value={`${keepCaptures.length} kept · ${captures.length - keepCaptures.length} discarded`}
                />
              </div>

              {/* Label editor */}
              {isPending && (
                <div className="rounded-md border p-3">
                  <Label className="text-xs">Label this person (optional)</Label>
                  <div className="mt-2 flex gap-2">
                    <Input
                      placeholder="e.g. Visitor in blue jacket"
                      value={labelDraft}
                      onChange={(e) => setLabelDraft(e.target.value)}
                      maxLength={128}
                      disabled={setLabel.isPending}
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleSaveLabel}
                      disabled={
                        setLabel.isPending ||
                        labelDraft.trim() === (cluster.label ?? "")
                      }
                    >
                      {setLabel.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      Save label
                    </Button>
                  </div>
                  <p className="mt-1.5 text-[11px] text-muted-foreground">
                    Just a working name — does not promote to an employee.
                  </p>
                </div>
              )}

              {/* Promoted/merged hints */}
              {cluster.status === "PROMOTED" && cluster.promoted_employee_id && (
                <div className="rounded-md border border-green-500/30 bg-green-500/10 p-3 text-xs">
                  This cluster has been added as employee #{cluster.promoted_employee_id}.
                  Their face is now recognized live by the cameras.
                </div>
              )}
              {cluster.status === "MERGED" && cluster.merged_into_cluster_id && (
                <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
                  Merged into cluster #{cluster.merged_into_cluster_id} during a
                  re-cluster pass.
                </div>
              )}

              {/* Captures grid */}
              <div className="space-y-2">
                <p className="text-sm font-medium">All captured faces</p>
                <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
                  {captures.map((cap) => (
                    <div
                      key={cap.id}
                      className={cn(
                        "overflow-hidden rounded-md border bg-card",
                        cap.status === "DISCARDED" && "opacity-50",
                      )}
                      title={`Captured ${format(new Date(cap.captured_at), "PPpp")}\nDet score ${cap.det_score.toFixed(2)} · Sharpness ${cap.sharpness_score.toFixed(0)}`}
                    >
                      <UnknownFaceImage
                        captureId={cap.id}
                        className="aspect-square w-full"
                      />
                      <div className="flex items-center gap-1 px-2 py-1 text-[10px] text-muted-foreground">
                        <Camera className="h-3 w-3" />
                        <span className="truncate">
                          {cap.camera_name ?? "—"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action footer */}
              <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
                {isPending && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmDiscard(true)}
                    disabled={discard.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                    Discard
                  </Button>
                )}
                {isPending && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPickerOpen(true)}
                    disabled={promoteExisting.isPending}
                  >
                    {promoteExisting.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Users className="h-4 w-4" />
                    )}
                    Add to existing employee…
                  </Button>
                )}
                {isPending && (
                  <Button
                    size="sm"
                    onClick={() => onPromoteNew(cluster)}
                  >
                    <UserPlus className="h-4 w-4" />
                    Add as new employee
                  </Button>
                )}
                {!isPending && (
                  <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                    Close
                  </Button>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Pick an existing employee */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Pick employee</DialogTitle>
            <DialogDescription>
              The cluster&apos;s captures will be appended as additional training
              images for the selected employee.
            </DialogDescription>
          </DialogHeader>
          <EmployeePicker value={pickedEmployee} onChange={setPickedEmployee} />
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={() => setPickerOpen(false)}
              disabled={promoteExisting.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => pickedEmployee && handlePromoteExisting(pickedEmployee)}
              disabled={!pickedEmployee || promoteExisting.isPending}
            >
              {promoteExisting.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Add captures to {pickedEmployee?.name ?? "…"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Discard confirmation */}
      <Dialog open={confirmDiscard} onOpenChange={setConfirmDiscard}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Discard this cluster?</DialogTitle>
            <DialogDescription>
              The cluster will be marked IGNORED. The face captures stay on disk
              for now and the next retention purge will remove them.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={() => setConfirmDiscard(false)}
              disabled={discard.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDiscard}
              disabled={discard.isPending}
            >
              {discard.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Discard
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Meta({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-medium">{value}</p>
    </div>
  );
}

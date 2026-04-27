"use client";

import {
  AlertTriangle,
  Eraser,
  Loader2,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { ClusterDetailDialog } from "@/components/unknowns/cluster-detail-dialog";
import { ClusterGrid } from "@/components/unknowns/cluster-grid";
import { PromoteNewDialog } from "@/components/unknowns/promote-new-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  usePurgeUnknowns,
  useRecluster,
  useUnknownClusterList,
} from "@/lib/hooks/use-unknowns";
import type {
  UnknownCluster,
  UnknownClusterDetail,
  UnknownClusterStatus,
} from "@/lib/types/unknowns";

const PAGE_SIZE = 24;

type StatusFilter = UnknownClusterStatus | "ALL";

export default function UnknownsPage() {
  const [status, setStatus] = useState<StatusFilter>("PENDING");
  const [labelQuery, setLabelQuery] = useState("");
  const [offset, setOffset] = useState(0);

  const [openClusterId, setOpenClusterId] = useState<number | null>(null);
  const [promoteCluster, setPromoteCluster] = useState<UnknownClusterDetail | null>(
    null,
  );
  const [purgeOpen, setPurgeOpen] = useState(false);

  const params = useMemo(
    () => ({
      status: status === "ALL" ? undefined : status,
      label: labelQuery.trim() || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [status, labelQuery, offset],
  );

  const { data, isLoading, isFetching } = useUnknownClusterList(params);
  const recluster = useRecluster();
  const purge = usePurgeUnknowns();

  function updateStatus(next: StatusFilter) {
    setStatus(next);
    setOffset(0);
  }

  function handleOpen(cluster: UnknownCluster) {
    setOpenClusterId(cluster.id);
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <PageHeader
        title="Unknown faces"
        description="Each card is one unique person the cameras saw who isn't an employee yet. Open a card to see all their captured faces and add them to the system."
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => recluster.mutate({})}
              disabled={recluster.isPending}
            >
              {recluster.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Re-cluster
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPurgeOpen(true)}
              disabled={purge.isPending}
            >
              <Eraser className="h-4 w-4" />
              Purge
            </Button>
          </>
        }
      />

      <Card className="flex flex-wrap items-end gap-3 p-4">
        <div className="flex flex-1 flex-col gap-1.5">
          <Label className="text-xs">Search by label</Label>
          <Input
            placeholder="e.g. Visitor"
            value={labelQuery}
            onChange={(e) => {
              setLabelQuery(e.target.value);
              setOffset(0);
            }}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Status</Label>
          <Select
            value={status}
            onValueChange={(v) => updateStatus(v as StatusFilter)}
          >
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="PENDING">Pending review</SelectItem>
              <SelectItem value="PROMOTED">Promoted</SelectItem>
              <SelectItem value="IGNORED">Discarded</SelectItem>
              <SelectItem value="MERGED">Merged</SelectItem>
              <SelectItem value="ALL">All</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Card>

      <ClusterGrid
        clusters={data?.items}
        loading={isLoading}
        onOpen={handleOpen}
      />

      <Card>
        <PaginationBar
          total={data?.total ?? 0}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={setOffset}
          loading={isFetching}
        />
      </Card>

      {/* Detail */}
      <ClusterDetailDialog
        open={openClusterId !== null}
        onOpenChange={(v) => !v && setOpenClusterId(null)}
        clusterId={openClusterId}
        onPromoteNew={(cluster) => {
          setPromoteCluster(cluster);
        }}
      />

      {/* Promote-to-new */}
      <PromoteNewDialog
        open={promoteCluster !== null}
        onOpenChange={(v) => !v && setPromoteCluster(null)}
        cluster={promoteCluster}
        onPromoted={() => {
          setPromoteCluster(null);
          setOpenClusterId(null);
        }}
      />

      {/* Purge */}
      <PurgeDialog
        open={purgeOpen}
        onOpenChange={setPurgeOpen}
        onConfirm={(maxAgeDays, includePromoted) => {
          purge.mutate(
            { max_age_days: maxAgeDays, include_promoted: includePromoted },
            { onSuccess: () => setPurgeOpen(false) },
          );
        }}
        submitting={purge.isPending}
      />
    </div>
  );
}

function PurgeDialog({
  open,
  onOpenChange,
  onConfirm,
  submitting,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onConfirm: (maxAgeDays: number | null, includePromoted: boolean) => void;
  submitting: boolean;
}) {
  const [days, setDays] = useState<number>(30);
  const [includePromoted, setIncludePromoted] = useState(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-warning" />
            Purge unknown captures
          </DialogTitle>
          <DialogDescription>
            Hard-deletes discarded and merged clusters older than the cutoff,
            including their face image files on disk. Pending clusters are{" "}
            <span className="font-medium">never</span> touched.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Older than (days)</Label>
            <Input
              type="number"
              min={1}
              max={3650}
              value={days}
              onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 1))}
              disabled={submitting}
            />
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input accent-primary"
              checked={includePromoted}
              onChange={(e) => setIncludePromoted(e.target.checked)}
              disabled={submitting}
            />
            Also reclaim disk for promoted clusters (their captures already exist
            as employee training images, so this just frees the originals)
          </label>
        </div>
        <Link
          href="/settings"
          className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
        >
          Default retention is the value of <code>unknown_retention_days</code> in
          Settings.
        </Link>
        <div className="flex justify-end gap-2 pt-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => onConfirm(days, includePromoted)}
            disabled={submitting}
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Purge {days}-day-old captures
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

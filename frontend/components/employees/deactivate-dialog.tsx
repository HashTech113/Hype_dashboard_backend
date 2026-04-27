"use client";

import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeactivateEmployee } from "@/lib/hooks/use-employees";
import type { Employee } from "@/lib/types/employee";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee: Employee | null;
}

export function DeactivateEmployeeDialog({
  open,
  onOpenChange,
  employee,
}: Props) {
  const mut = useDeactivateEmployee();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Deactivate {employee?.name}?</DialogTitle>
          <DialogDescription>
            The record is kept for history (attendance events reference it), but
            the employee will no longer be recognized by the camera pipeline or
            appear in presence lists. You can reactivate from the edit dialog at
            any time.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mut.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={mut.isPending || !employee}
            onClick={() =>
              employee &&
              mut.mutate(employee.id, {
                onSuccess: () => onOpenChange(false),
              })
            }
          >
            {mut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Deactivate
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

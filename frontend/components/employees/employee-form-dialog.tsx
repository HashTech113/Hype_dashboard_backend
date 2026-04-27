"use client";

import { useEffect } from "react";

import { EmployeeForm } from "@/components/employees/employee-form";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useCreateEmployee,
  useUpdateEmployee,
} from "@/lib/hooks/use-employees";
import type { Employee } from "@/lib/types/employee";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee?: Employee | null;
}

export function EmployeeFormDialog({ open, onOpenChange, employee }: Props) {
  const isEdit = !!employee;
  const createMut = useCreateEmployee();
  const updateMut = useUpdateEmployee();
  const submitting = createMut.isPending || updateMut.isPending;

  useEffect(() => {
    if (!open) {
      createMut.reset();
      updateMut.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit employee" : "Add employee"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the employee's profile. Changes apply immediately."
              : "Create an employee record. You can enroll face images right after."}
          </DialogDescription>
        </DialogHeader>

        {isEdit ? (
          <EmployeeForm
            mode="edit"
            initial={employee!}
            submitting={submitting}
            onCancel={() => onOpenChange(false)}
            onSubmit={(payload) =>
              updateMut.mutate(
                { id: employee!.id, payload },
                { onSuccess: () => onOpenChange(false) },
              )
            }
          />
        ) : (
          <EmployeeForm
            mode="create"
            submitting={submitting}
            onCancel={() => onOpenChange(false)}
            onSubmit={(payload) =>
              createMut.mutate(payload, {
                onSuccess: () => onOpenChange(false),
              })
            }
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

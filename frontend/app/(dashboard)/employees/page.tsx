"use client";

import { Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { DeactivateEmployeeDialog } from "@/components/employees/deactivate-dialog";
import {
  EmployeeFilters,
  type EmployeeFiltersState,
} from "@/components/employees/employee-filters";
import { EmployeeFormDialog } from "@/components/employees/employee-form-dialog";
import { EmployeeTable } from "@/components/employees/employee-table";
import { PageHeader } from "@/components/shared/page-header";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useEmployeeList } from "@/lib/hooks/use-employees";
import type { Employee } from "@/lib/types/employee";

const PAGE_SIZE = 25;

function toApiActive(v: EmployeeFiltersState["active"]): boolean | undefined {
  if (v === "all") return undefined;
  return v === "active";
}

export default function EmployeesPage() {
  const [filters, setFilters] = useState<EmployeeFiltersState>({
    q: "",
    department: "",
    active: "all",
  });
  const [offset, setOffset] = useState(0);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Employee | null>(null);
  const [deactivating, setDeactivating] = useState<Employee | null>(null);

  const params = useMemo(
    () => ({
      q: filters.q.trim() || undefined,
      department: filters.department || undefined,
      is_active: toApiActive(filters.active),
      limit: PAGE_SIZE,
      offset,
    }),
    [filters, offset],
  );

  const { data, isLoading, isFetching } = useEmployeeList(params);

  const departments = useMemo(() => {
    const set = new Set<string>();
    for (const r of data?.items ?? []) {
      if (r.department) set.add(r.department);
    }
    return Array.from(set).sort();
  }, [data]);

  function updateFilters(next: EmployeeFiltersState) {
    setFilters(next);
    setOffset(0);
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <PageHeader
        title="Employees"
        description="Manage staff records, roles, and training eligibility."
        actions={
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus className="h-4 w-4" />
            Add employee
          </Button>
        }
      />

      <Card>
        <div className="border-b p-4">
          <EmployeeFilters
            value={filters}
            onChange={updateFilters}
            departments={departments}
          />
        </div>
        <EmployeeTable
          rows={data?.items}
          loading={isLoading}
          onEdit={(e) => {
            setEditing(e);
            setFormOpen(true);
          }}
          onDeactivate={(e) => setDeactivating(e)}
        />
        <PaginationBar
          total={data?.total ?? 0}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={setOffset}
          loading={isFetching}
        />
      </Card>

      <EmployeeFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        employee={editing}
      />
      <DeactivateEmployeeDialog
        open={!!deactivating}
        onOpenChange={(v) => !v && setDeactivating(null)}
        employee={deactivating}
      />
    </div>
  );
}

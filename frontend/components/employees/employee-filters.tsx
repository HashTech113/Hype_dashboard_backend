"use client";

import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface EmployeeFiltersState {
  q: string;
  department: string;
  active: "all" | "active" | "inactive";
}

interface Props {
  value: EmployeeFiltersState;
  onChange: (next: EmployeeFiltersState) => void;
  departments: string[];
}

export function EmployeeFilters({ value, onChange, departments }: Props) {
  const hasFilters =
    value.q.length > 0 ||
    value.department.length > 0 ||
    value.active !== "all";

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={value.q}
          onChange={(e) => onChange({ ...value, q: e.target.value })}
          placeholder="Search name, code, or email"
          className="pl-9"
        />
      </div>
      <Select
        value={value.department || "__all"}
        onValueChange={(v) =>
          onChange({ ...value, department: v === "__all" ? "" : v })
        }
      >
        <SelectTrigger className="w-full sm:w-48">
          <SelectValue placeholder="Department" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all">All departments</SelectItem>
          {departments.map((d) => (
            <SelectItem key={d} value={d}>
              {d}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={value.active}
        onValueChange={(v) =>
          onChange({ ...value, active: v as EmployeeFiltersState["active"] })
        }
      >
        <SelectTrigger className="w-full sm:w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All status</SelectItem>
          <SelectItem value="active">Active</SelectItem>
          <SelectItem value="inactive">Inactive</SelectItem>
        </SelectContent>
      </Select>
      {hasFilters && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onChange({ q: "", department: "", active: "all" })
          }
        >
          <X className="h-4 w-4" />
          Clear
        </Button>
      )}
    </div>
  );
}

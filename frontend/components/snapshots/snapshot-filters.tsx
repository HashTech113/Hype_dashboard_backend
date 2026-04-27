"use client";

import { X } from "lucide-react";

import { EmployeePicker } from "@/components/training/employee-picker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { EventType } from "@/lib/types/attendance";
import type { Employee } from "@/lib/types/employee";

export type GroupMode = "date" | "employee" | "none";

export interface SnapshotFiltersState {
  employee: Employee | null;
  dateFrom: string;
  dateTo: string;
  eventType: EventType | "ALL";
  group: GroupMode;
}

interface Props {
  value: SnapshotFiltersState;
  onChange: (next: SnapshotFiltersState) => void;
}

export function SnapshotFilters({ value, onChange }: Props) {
  const isEmpty =
    !value.employee &&
    !value.dateFrom &&
    !value.dateTo &&
    value.eventType === "ALL";

  return (
    <div className="grid gap-3 md:grid-cols-[1.2fr,_1fr,_1fr,_1fr,_1fr,_auto]">
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Employee</Label>
        <EmployeePicker
          value={value.employee}
          onChange={(e) => onChange({ ...value, employee: e })}
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground" htmlFor="sn-from">
          From
        </Label>
        <Input
          id="sn-from"
          type="date"
          value={value.dateFrom}
          onChange={(e) => onChange({ ...value, dateFrom: e.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground" htmlFor="sn-to">
          To
        </Label>
        <Input
          id="sn-to"
          type="date"
          value={value.dateTo}
          onChange={(e) => onChange({ ...value, dateTo: e.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Event type</Label>
        <Select
          value={value.eventType}
          onValueChange={(v) =>
            onChange({ ...value, eventType: v as EventType | "ALL" })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All events</SelectItem>
            <SelectItem value="IN">IN</SelectItem>
            <SelectItem value="BREAK_OUT">Break out</SelectItem>
            <SelectItem value="BREAK_IN">Break in</SelectItem>
            <SelectItem value="OUT">OUT</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Group by</Label>
        <Select
          value={value.group}
          onValueChange={(v) =>
            onChange({ ...value, group: v as GroupMode })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="date">Date</SelectItem>
            <SelectItem value="employee">Employee</SelectItem>
            <SelectItem value="none">None (flat)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-end">
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onChange({
              ...value,
              employee: null,
              dateFrom: "",
              dateTo: "",
              eventType: "ALL",
            })
          }
          disabled={isEmpty}
        >
          <X className="h-4 w-4" />
          Clear
        </Button>
      </div>
    </div>
  );
}

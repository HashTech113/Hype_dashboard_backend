"use client";

import { ChevronDown, Search, User } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useEmployeeList } from "@/lib/hooks/use-employees";
import type { Employee } from "@/lib/types/employee";
import { cn } from "@/lib/utils";

interface Props {
  value: Employee | null;
  onChange: (employee: Employee | null) => void;
}

function initials(name: string, code: string): string {
  const src = (name || code || "").trim();
  const parts = src.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function EmployeePicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const params = useMemo(
    () => ({ q: q.trim() || undefined, is_active: true, limit: 25, offset: 0 }),
    [q],
  );
  const { data, isLoading } = useEmployeeList(params);

  useEffect(() => {
    if (!open) setQ("");
  }, [open]);

  return (
    <>
      <Button
        variant="outline"
        className={cn(
          "h-auto w-full justify-start gap-3 px-3 py-2 text-left",
          !value && "text-muted-foreground",
        )}
        onClick={() => setOpen(true)}
      >
        {value ? (
          <>
            <Avatar className="h-8 w-8">
              <AvatarFallback className="text-xs">
                {initials(value.name, value.employee_code)}
              </AvatarFallback>
            </Avatar>
            <span className="flex min-w-0 flex-1 flex-col leading-tight">
              <span className="truncate font-medium text-foreground">
                {value.name}
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {value.employee_code}
                {value.department ? ` · ${value.department}` : ""}
              </span>
            </span>
          </>
        ) : (
          <>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
              <User className="h-4 w-4 text-muted-foreground" />
            </div>
            <span>Select an employee…</span>
          </>
        )}
        <ChevronDown className="ml-auto h-4 w-4 opacity-60" />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Select employee</DialogTitle>
          </DialogHeader>

          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search name, code, or email"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-9"
              autoFocus
            />
          </div>

          <div className="max-h-80 overflow-y-auto rounded-md border">
            {isLoading ? (
              <ul className="divide-y">
                {Array.from({ length: 5 }).map((_, i) => (
                  <li key={i} className="flex items-center gap-3 p-3">
                    <Skeleton className="h-8 w-8 rounded-full" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-3 w-40" />
                      <Skeleton className="h-3 w-28" />
                    </div>
                  </li>
                ))}
              </ul>
            ) : !data?.items || data.items.length === 0 ? (
              <p className="p-6 text-center text-sm text-muted-foreground">
                No employees match your search.
              </p>
            ) : (
              <ul className="divide-y">
                {data.items.map((e) => (
                  <li key={e.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onChange(e);
                        setOpen(false);
                      }}
                      className={cn(
                        "flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-accent",
                        value?.id === e.id && "bg-accent/60",
                      )}
                    >
                      <Avatar className="h-8 w-8">
                        <AvatarFallback className="text-xs">
                          {initials(e.name, e.employee_code)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{e.name}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {e.employee_code}
                          {e.department ? ` · ${e.department}` : ""}
                        </p>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

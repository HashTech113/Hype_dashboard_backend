"use client";

import { MoreHorizontal, Pencil, ScanFace, UserX } from "lucide-react";
import Link from "next/link";

import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Employee } from "@/lib/types/employee";

interface Props {
  rows: Employee[] | undefined;
  loading: boolean;
  onEdit: (e: Employee) => void;
  onDeactivate: (e: Employee) => void;
}

function initials(name: string, code: string): string {
  const src = (name || code || "").trim();
  const parts = src.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function EmployeeTable({ rows, loading, onEdit, onDeactivate }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[30%]">Employee</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Department</TableHead>
          <TableHead>Contact</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="w-12" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <TableRow key={`s-${i}`}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <Skeleton className="h-9 w-9 rounded-full" />
                  <div className="flex flex-col gap-1.5">
                    <Skeleton className="h-3 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-32" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-5 w-16 rounded-full" />
              </TableCell>
              <TableCell />
            </TableRow>
          ))
        ) : !rows || rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={6} className="py-12 text-center">
              <p className="text-sm text-muted-foreground">
                No employees match these filters.
              </p>
            </TableCell>
          </TableRow>
        ) : (
          rows.map((e) => (
            <TableRow key={e.id}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="text-xs">
                      {initials(e.name, e.employee_code)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{e.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {e.employee_code}
                    </p>
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {e.designation || "—"}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {e.department || "—"}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                <div className="flex flex-col leading-tight">
                  <span className="truncate">{e.email || "—"}</span>
                  {e.phone && (
                    <span className="text-xs opacity-80">{e.phone}</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                {e.is_active ? (
                  <Badge variant="success">Active</Badge>
                ) : (
                  <Badge variant="secondary">Inactive</Badge>
                )}
              </TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label="Actions">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-44">
                    <DropdownMenuItem onClick={() => onEdit(e)}>
                      <Pencil className="mr-2 h-4 w-4" /> Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link href={`/training?employee=${e.id}`}>
                        <ScanFace className="mr-2 h-4 w-4" /> Train faces
                      </Link>
                    </DropdownMenuItem>
                    {e.is_active && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => onDeactivate(e)}
                        >
                          <UserX className="mr-2 h-4 w-4" /> Deactivate
                        </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}

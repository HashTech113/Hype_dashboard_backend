"use client";

import { LogOut, ShieldCheck } from "lucide-react";

import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth/context";

function initials(input: string | null | undefined): string {
  if (!input) return "?";
  const parts = input.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function UserMenu() {
  const { admin, logout } = useAuth();

  if (!admin) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="gap-2 pl-1.5 pr-2">
          <Avatar className="h-7 w-7">
            <AvatarFallback className="text-xs">
              {initials(admin.full_name || admin.username)}
            </AvatarFallback>
          </Avatar>
          <div className="hidden text-left leading-tight sm:block">
            <p className="text-sm font-medium">
              {admin.full_name || admin.username}
            </p>
            <p className="text-[11px] text-muted-foreground">{admin.role}</p>
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>
          <div className="leading-tight">
            <p className="text-sm font-medium">
              {admin.full_name || admin.username}
            </p>
            <p className="text-xs font-normal text-muted-foreground">
              {admin.username}
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled>
          <ShieldCheck className="mr-2 h-4 w-4" /> {admin.role}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout} className="text-destructive">
          <LogOut className="mr-2 h-4 w-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

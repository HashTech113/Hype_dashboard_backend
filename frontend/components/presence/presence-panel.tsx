"use client";

import { Input } from "@/components/ui/input";
import { useMemo, useState } from "react";

import { PresenceTable } from "@/components/presence/presence-table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePresence } from "@/lib/hooks/use-presence";
import type { PresenceEntry, PresenceStatus } from "@/lib/types/presence";

type TabKey = "all" | PresenceStatus;

const TAB_ORDER: TabKey[] = ["all", "INSIDE", "ON_BREAK", "OUTSIDE", "ABSENT"];

const TAB_LABEL: Record<TabKey, string> = {
  all: "All",
  INSIDE: "Inside",
  ON_BREAK: "On break",
  OUTSIDE: "Outside",
  ABSENT: "Absent",
};

function countByStatus(rows: PresenceEntry[] | undefined) {
  const counts: Record<TabKey, number> = {
    all: 0,
    INSIDE: 0,
    ON_BREAK: 0,
    OUTSIDE: 0,
    ABSENT: 0,
  };
  if (!rows) return counts;
  counts.all = rows.length;
  for (const r of rows) counts[r.status] += 1;
  return counts;
}

function filterRows(
  rows: PresenceEntry[] | undefined,
  tab: TabKey,
  query: string,
): PresenceEntry[] {
  if (!rows) return [];
  const q = query.trim().toLowerCase();
  return rows.filter((r) => {
    if (tab !== "all" && r.status !== tab) return false;
    if (!q) return true;
    return (
      r.employee_name.toLowerCase().includes(q) ||
      r.employee_code.toLowerCase().includes(q) ||
      (r.department ?? "").toLowerCase().includes(q)
    );
  });
}

export function PresencePanel() {
  const { data, isLoading } = usePresence();
  const [tab, setTab] = useState<TabKey>("all");
  const [query, setQuery] = useState("");

  const counts = useMemo(() => countByStatus(data), [data]);
  const rows = useMemo(() => filterRows(data, tab, query), [data, tab, query]);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>Live employee status</CardTitle>
            <CardDescription>
              Current presence for every active employee · auto-refreshes every
              10 seconds
            </CardDescription>
          </div>
          <Input
            placeholder="Search name, code, or department"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full sm:max-w-xs"
          />
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
          <TabsList className="flex w-full flex-wrap gap-1 sm:w-auto">
            {TAB_ORDER.map((k) => (
              <TabsTrigger key={k} value={k} className="gap-2">
                <span>{TAB_LABEL[k]}</span>
                <span className="rounded-full bg-muted-foreground/10 px-2 py-0.5 text-[10px] font-semibold tabular-nums">
                  {counts[k]}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
          {TAB_ORDER.map((k) => (
            <TabsContent key={k} value={k} className="mt-4">
              <div className="rounded-md border">
                <PresenceTable
                  rows={tab === k ? rows : undefined}
                  loading={isLoading}
                />
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}

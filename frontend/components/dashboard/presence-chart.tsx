"use client";

import { Users } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardSnapshot } from "@/lib/hooks/use-dashboard";
import { cn } from "@/lib/utils";

interface Slice {
  key: string;
  label: string;
  value: number;
  color: string;
}

function tooltipFormatter(
  value: number,
  _name: string,
  item: { payload?: Slice },
): (string | React.ReactElement)[] {
  return [
    <span key="v" className="font-medium">
      {value}
    </span>,
    item.payload?.label ?? "",
  ];
}

export function PresenceChart() {
  const { data, isLoading } = useDashboardSnapshot();

  const slices: Slice[] = [
    {
      key: "inside",
      label: "Inside office",
      value: data?.inside_office ?? 0,
      color: "hsl(142 71% 45%)",
    },
    {
      key: "on_break",
      label: "On break",
      value: data?.on_break ?? 0,
      color: "hsl(35 92% 50%)",
    },
    {
      key: "outside",
      label: "Outside",
      value: data?.outside_office ?? 0,
      color: "hsl(217 91% 60%)",
    },
    {
      key: "absent",
      label: "Absent",
      value: data?.absent_today ?? 0,
      color: "hsl(215 20% 65%)",
    },
  ];

  const total = slices.reduce((acc, s) => acc + s.value, 0);
  const active = data?.active_employees ?? 0;

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>Presence breakdown</CardTitle>
            <CardDescription>Where the team is right now</CardDescription>
          </div>
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Users className="h-4 w-4" />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[240px] w-full rounded-xl" />
        ) : total === 0 ? (
          <div className="flex h-[240px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Users className="h-5 w-5" />
            No attendance activity yet today.
          </div>
        ) : (
          <div className="grid grid-cols-[1fr,_auto] items-center gap-6">
            <div className="relative h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Tooltip
                    cursor={{ fill: "transparent" }}
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    formatter={tooltipFormatter}
                  />
                  <Pie
                    data={slices}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={62}
                    outerRadius={92}
                    strokeWidth={2}
                    stroke="hsl(var(--background))"
                    paddingAngle={2}
                  >
                    {slices.map((slice) => (
                      <Cell key={slice.key} fill={slice.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <p className="text-3xl font-semibold tabular-nums">{active}</p>
                <p className="text-xs text-muted-foreground">active</p>
              </div>
            </div>
            <ul className="flex flex-col gap-2.5">
              {slices.map((s) => {
                const pct =
                  active > 0 ? Math.round((s.value / active) * 100) : 0;
                return (
                  <li
                    key={s.key}
                    className="flex items-center justify-between gap-4 text-sm"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-sm"
                        style={{ background: s.color }}
                      />
                      <span className="text-muted-foreground">{s.label}</span>
                    </span>
                    <span className="tabular-nums font-medium">
                      {s.value}
                      <span
                        className={cn(
                          "ml-2 text-xs font-normal text-muted-foreground",
                          s.value === 0 && "opacity-50",
                        )}
                      >
                        {pct}%
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

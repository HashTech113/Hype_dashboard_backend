"use client";

import { format, parseISO } from "date-fns";
import { Activity } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEventsByHour } from "@/lib/hooks/use-dashboard";

interface Point {
  label: string;
  full: string;
  count: number;
}

function prepare(data?: { bucket_start: string; count: number }[]): Point[] {
  if (!data) return [];
  return data.map((b) => {
    const dt = parseISO(b.bucket_start);
    return {
      label: format(dt, "HH:mm"),
      full: format(dt, "PPpp"),
      count: b.count,
    };
  });
}

export function EventsChart() {
  const { data, isLoading } = useEventsByHour(24);
  const points = prepare(data);
  const total = points.reduce((acc, p) => acc + p.count, 0);

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>Events · last 24 hours</CardTitle>
            <CardDescription>
              {total > 0 ? `${total} events across the period` : "Hourly attendance events"}
            </CardDescription>
          </div>
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Activity className="h-4 w-4" />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[240px] w-full rounded-xl" />
        ) : total === 0 ? (
          <div className="flex h-[240px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Activity className="h-5 w-5" />
            No events recorded in the last 24 hours.
          </div>
        ) : (
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={points}
                margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="eventsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  vertical={false}
                  stroke="hsl(var(--border))"
                  strokeDasharray="4 4"
                />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={false}
                  fontSize={11}
                  interval={Math.max(1, Math.floor(points.length / 8))}
                  tick={{ fill: "hsl(var(--muted-foreground))" }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  fontSize={11}
                  width={30}
                  allowDecimals={false}
                  tick={{ fill: "hsl(var(--muted-foreground))" }}
                />
                <Tooltip
                  cursor={{
                    stroke: "hsl(var(--primary))",
                    strokeOpacity: 0.2,
                    strokeWidth: 1.5,
                  }}
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelFormatter={(_label, payload) => {
                    const p = payload?.[0]?.payload as Point | undefined;
                    return p?.full ?? "";
                  }}
                  formatter={(value: number) => [`${value} events`, ""]}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  fill="url(#eventsFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

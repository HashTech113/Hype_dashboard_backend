import { LucideIcon } from "lucide-react";
import { ReactNode } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  description: string;
  icon: LucideIcon;
  tone?: "primary" | "success" | "warning" | "default";
  children: ReactNode;
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  primary: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  default: "bg-muted text-muted-foreground",
};

export function ReportCardShell({
  title,
  description,
  icon: Icon,
  tone = "default",
  children,
}: Props) {
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <div
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
              TONE[tone],
            )}
          >
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-end">
        {children}
      </CardContent>
    </Card>
  );
}

"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCameras } from "@/lib/hooks/use-cameras";

interface Props {
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
}

export function CameraPicker({ value, onChange, disabled }: Props) {
  const { data, isLoading } = useCameras();
  const active = (data ?? []).filter((c) => c.is_active);

  return (
    <Select
      value={value ? String(value) : ""}
      onValueChange={(v) => onChange(v ? Number(v) : null)}
      disabled={disabled || isLoading}
    >
      <SelectTrigger className="w-full">
        <SelectValue placeholder={isLoading ? "Loading cameras…" : "Choose camera"} />
      </SelectTrigger>
      <SelectContent>
        {active.length === 0 ? (
          <SelectItem value="__none" disabled>
            No active cameras
          </SelectItem>
        ) : (
          active.map((c) => (
            <SelectItem key={c.id} value={String(c.id)}>
              {c.name} · {c.camera_type}
              {c.location ? ` · ${c.location}` : ""}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  );
}

"use client";

/**
 * Camera Wizard — the no-RTSP-knowledge-required onboarding flow.
 *
 * Steps:
 *   1. Network reminder (plug Ethernet from PoE switch into AI PC)
 *   2. Credentials (IP, username, password) — no URL required
 *   3. Smart probe with live progress (TCP → TLS → ONVIF → vendor patterns)
 *   4. Pick name + ENTRY/EXIT + optional FPS
 *   5. Confirm & save
 *
 * The wizard is intentionally non-modal-feeling: each step is a discrete
 * panel, navigation is forward-only (with Back), and the probe failures
 * surface actionable suggestions inline so the operator can fix and retry
 * without leaving the wizard.
 */

import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  PlugZap,
  Search,
  Sparkles,
  Video,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useConnectSmart, useSmartProbe } from "@/lib/hooks/use-cameras";
import type {
  CameraType,
  SmartProbeResult,
  SmartProbeStep,
} from "@/lib/types/camera";
import { cn } from "@/lib/utils";

interface CameraWizardDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Pre-fill the IP address field — set by the LAN-discovery flow so
   *  the operator only types credentials. Step jumps directly to Step 2. */
  prefillHost?: string;
}

type WizardStep = 1 | 2 | 3 | 4;

interface FormState {
  host: string;
  port: number;
  username: string;
  password: string;
  name: string;
  camera_type: CameraType;
  location: string;
  fps_override: string; // "" = global
  prefer_sub_stream: boolean;
}

const DEFAULT_STATE: FormState = {
  host: "",
  port: 554,
  username: "admin",
  password: "",
  name: "",
  camera_type: "ENTRY",
  location: "",
  fps_override: "",
  prefer_sub_stream: true,
};

export function CameraWizardDialog({
  open,
  onOpenChange,
  prefillHost,
}: CameraWizardDialogProps) {
  const [step, setStep] = useState<WizardStep>(1);
  const [state, setState] = useState<FormState>(DEFAULT_STATE);
  const [probeResult, setProbeResult] = useState<SmartProbeResult | null>(null);

  const probe = useSmartProbe();
  const connect = useConnectSmart();

  useEffect(() => {
    if (open) {
      // If we got here from auto-discovery, jump straight to credentials
      // and prefill the IP so the operator only types user/password.
      if (prefillHost) {
        setStep(2);
        setState({ ...DEFAULT_STATE, host: prefillHost });
      } else {
        setStep(1);
        setState(DEFAULT_STATE);
      }
      setProbeResult(null);
      probe.reset();
      connect.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, prefillHost]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((s) => ({ ...s, [key]: value }));
  }

  function runProbe() {
    setProbeResult(null);
    probe.mutate(
      {
        name: state.name || "wizard-probe",
        camera_type: state.camera_type,
        host: state.host.trim(),
        port: state.port,
        username: state.username.trim(),
        password: state.password,
        prefer_sub_stream: state.prefer_sub_stream,
        probe_timeout_seconds: 30,
      },
      { onSuccess: (res) => setProbeResult(res) },
    );
  }

  function runConnect() {
    if (!probeResult?.ok || !state.name.trim()) return;
    const fps = state.fps_override.trim();
    connect.mutate(
      {
        name: state.name.trim(),
        camera_type: state.camera_type,
        location: state.location.trim() || null,
        host: state.host.trim(),
        port: state.port,
        username: state.username.trim(),
        password: state.password,
        prefer_sub_stream: state.prefer_sub_stream,
        probe_timeout_seconds: 30,
        is_active: true,
        fps_override: fps ? +fps : null,
      },
      {
        onSuccess: (res) => {
          if (res.camera) {
            onOpenChange(false);
          }
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Add Camera &mdash; Smart Connect
          </DialogTitle>
          <DialogDescription>
            We&apos;ll auto-discover your camera&apos;s RTSP URL. You only need the IP, username, and password.
          </DialogDescription>
        </DialogHeader>

        <ProgressDots step={step} />

        {step === 1 && (
          <Step1Network onNext={() => setStep(2)} onCancel={() => onOpenChange(false)} />
        )}
        {step === 2 && (
          <Step2Credentials
            state={state}
            update={update}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <Step3Probe
            state={state}
            probeResult={probeResult}
            isProbing={probe.isPending}
            onProbe={runProbe}
            onBack={() => setStep(2)}
            onNext={() => setStep(4)}
          />
        )}
        {step === 4 && (
          <Step4Save
            state={state}
            update={update}
            probeResult={probeResult}
            isSaving={connect.isPending}
            onBack={() => setStep(3)}
            onSave={runConnect}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProgressDots({ step }: { step: WizardStep }) {
  const labels = ["Network", "Credentials", "Probe", "Save"];
  return (
    <div className="mb-4 flex items-center justify-center gap-2">
      {labels.map((label, i) => {
        const idx = (i + 1) as WizardStep;
        const active = idx <= step;
        return (
          <div key={label} className="flex items-center gap-2">
            <div
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-muted text-muted-foreground",
              )}
            >
              {idx === step ? idx : active ? <CheckCircle2 className="h-4 w-4" /> : idx}
            </div>
            <span
              className={cn(
                "text-xs",
                active ? "text-foreground" : "text-muted-foreground",
              )}
            >
              {label}
            </span>
            {i < labels.length - 1 && (
              <div className="mx-1 h-px w-4 bg-border" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function Step1Network({ onNext, onCancel }: { onNext: () => void; onCancel: () => void }) {
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-primary/30 bg-primary/5 p-4">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <PlugZap className="h-4 w-4 text-primary" />
          Before you start
        </h3>
        <ol className="ml-6 list-decimal space-y-1 text-sm text-muted-foreground">
          <li>Make sure the camera&apos;s Ethernet cable is plugged into the PoE switch.</li>
          <li>Plug the PoE switch&apos;s Ethernet cable into THIS PC&apos;s LAN port.</li>
          <li>
            On this PC&apos;s LAN adapter, set a static IP on the camera subnet (typically <code className="text-xs">192.168.1.50</code> / mask <code className="text-xs">255.255.255.0</code>).
          </li>
          <li>You can verify by opening <code className="text-xs">http://&lt;camera-IP&gt;</code> in a browser and seeing the camera&apos;s login page.</li>
        </ol>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={onNext}>
          I&apos;m ready
          <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function Step2Credentials({
  state,
  update,
  onBack,
  onNext,
}: {
  state: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const isValid =
    state.host.trim().length > 0 &&
    state.username.trim().length > 0 &&
    state.password.length > 0;

  // Detect if user pasted whole URL into the IP field — be helpful.
  const looksLikeUrl = state.host.includes("://") || state.host.includes("@");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="sm:col-span-2 space-y-1.5">
          <Label>
            Camera IP <span className="text-destructive">*</span>
          </Label>
          <Input
            placeholder="192.168.1.201"
            value={state.host}
            onChange={(e) => update("host", e.target.value)}
            autoFocus
            className="font-mono"
          />
          {looksLikeUrl && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              Just the IP here, not the full URL — we&apos;ll discover the URL for you.
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>Port</Label>
          <Input
            type="number"
            min={1}
            max={65535}
            value={state.port}
            onChange={(e) => update("port", +e.target.value || 554)}
          />
          {state.port !== 554 && state.port !== 322 ? (
            <p className="text-[11px] text-amber-600 dark:text-amber-500">
              ⚠ {state.port} is not a standard RTSP port. RTSP is on 554 even
              when port scanners show 80, 8000, or 8080 as open (those are the
              camera&apos;s web UI / SDK ports, not RTSP).
            </p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              554 = RTSP (plain), 322 = RTSPS (TLS). The backend auto-detects
              TLS — leave at 554 unless you know the camera enforces RTSPS.
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>
            Username <span className="text-destructive">*</span>
          </Label>
          <Input
            placeholder="admin"
            value={state.username}
            onChange={(e) => update("username", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>
            Password <span className="text-destructive">*</span>
          </Label>
          <Input
            type="password"
            placeholder="Admin@123"
            value={state.password}
            onChange={(e) => update("password", e.target.value)}
          />
          <p className="text-[11px] text-muted-foreground">
            Special characters (<code className="text-[10px]">@</code>, <code className="text-[10px]">:</code>) are fine — we encode them automatically.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-md border bg-muted/30 p-3 text-xs">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-input accent-primary"
          checked={state.prefer_sub_stream}
          onChange={(e) => update("prefer_sub_stream", e.target.checked)}
          id="prefer-sub"
        />
        <label htmlFor="prefer-sub" className="cursor-pointer">
          Use the lower-resolution sub-stream (recommended &mdash; lighter on CPU, plenty for face detection)
        </label>
      </div>

      <div className="flex justify-between gap-2">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        <Button onClick={onNext} disabled={!isValid}>
          Probe camera
          <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function Step3Probe({
  state,
  probeResult,
  isProbing,
  onProbe,
  onBack,
  onNext,
}: {
  state: FormState;
  probeResult: SmartProbeResult | null;
  isProbing: boolean;
  onProbe: () => void;
  onBack: () => void;
  onNext: () => void;
}) {
  // Auto-start the probe the first time we land on this step.
  useEffect(() => {
    if (probeResult === null && !isProbing) {
      onProbe();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="rounded-md border bg-muted/20 p-3">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <Search className="h-4 w-4" />
          Discovering {state.host}:{state.port}
        </h3>
        <p className="text-xs text-muted-foreground">
          Walking the discovery ladder &mdash; this takes up to 20 seconds depending on your camera.
        </p>
      </div>

      <StepsList steps={probeResult?.steps ?? []} isProbing={isProbing} />

      {probeResult && !isProbing && (
        <div
          className={cn(
            "rounded-md border p-3 text-sm",
            probeResult.ok
              ? "border-green-500/30 bg-green-500/10"
              : "border-destructive/40 bg-destructive/10",
          )}
        >
          <div className="flex items-start gap-2">
            {probeResult.ok ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
            ) : (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            )}
            <div className="space-y-1">
              <p className="font-medium">{probeResult.summary}</p>
              {probeResult.ok && probeResult.working_url && (
                <p className="break-all font-mono text-[11px] text-muted-foreground">
                  {probeResult.working_url.replace(/\/\/[^@]+@/, "//***:***@")}
                </p>
              )}
              {probeResult.vendor_hint && (
                <p className="text-xs text-muted-foreground">
                  Detected: <Badge variant="outline">{probeResult.vendor_hint}</Badge>
                </p>
              )}
              {probeResult.ok && probeResult.width && probeResult.height && (
                <p className="text-xs text-muted-foreground">
                  Stream: {probeResult.width} &times; {probeResult.height}
                </p>
              )}
              {!probeResult.ok && probeResult.suggestion && (
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium">Try:</span> {probeResult.suggestion}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="flex justify-between gap-2">
        <Button variant="outline" onClick={onBack} disabled={isProbing}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={onProbe}
            disabled={isProbing}
          >
            {isProbing && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {probeResult ? "Probe again" : "Probing..."}
          </Button>
          <Button onClick={onNext} disabled={!probeResult?.ok || isProbing}>
            Continue
            <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function StepsList({
  steps,
  isProbing,
}: {
  steps: SmartProbeStep[];
  isProbing: boolean;
}) {
  if (steps.length === 0 && isProbing) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-md border bg-muted/20 p-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Starting discovery...
      </div>
    );
  }
  if (steps.length === 0) return null;
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/20 p-3">
      {steps.map((s, i) => (
        <div key={`${s.name}-${i}`} className="flex items-start gap-2 text-xs">
          {s.ok ? (
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-600" />
          ) : (
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
          )}
          <div className="flex-1">
            <p>
              <span className="font-mono font-medium">{s.name}</span> &mdash; {s.detail}
              <span className="ml-1.5 text-muted-foreground">({s.duration_ms} ms)</span>
            </p>
            {s.error && (
              <p className="mt-0.5 text-[11px] text-destructive">{s.error}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function Step4Save({
  state,
  update,
  probeResult,
  isSaving,
  onBack,
  onSave,
}: {
  state: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  probeResult: SmartProbeResult | null;
  isSaving: boolean;
  onBack: () => void;
  onSave: () => void;
}) {
  const canSave = state.name.trim().length > 0 && probeResult?.ok;
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-green-500/30 bg-green-500/10 p-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Video className="h-4 w-4 text-green-600" />
          Working URL found
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {probeResult?.width && probeResult?.height
            ? `${probeResult.width} × ${probeResult.height} via ${probeResult.strategy}`
            : `via ${probeResult?.strategy}`}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <div className="space-y-1.5">
          <Label>
            Camera name <span className="text-destructive">*</span>
          </Label>
          <Input
            placeholder="Office cam 1, Front door, Reception …"
            value={state.name}
            onChange={(e) => update("name", e.target.value)}
            autoFocus
          />
          <p className="text-[11px] text-muted-foreground">
            A short label that identifies where this camera is. Shown above
            its live tile.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Location (optional)</Label>
          <Input
            placeholder="Reception, ground floor"
            value={state.location}
            onChange={(e) => update("location", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>FPS override (optional)</Label>
          <Input
            type="number"
            min={1}
            max={30}
            placeholder="(use global)"
            value={state.fps_override}
            onChange={(e) => update("fps_override", e.target.value)}
          />
          <p className="text-[11px] text-muted-foreground">
            Blank = inherit global. Lower (e.g. 2) for low-traffic doors.
          </p>
        </div>
      </div>

      <div className="flex justify-between gap-2">
        <Button variant="outline" onClick={onBack} disabled={isSaving}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        <Button onClick={onSave} disabled={!canSave || isSaving}>
          {isSaving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          Save and start camera
        </Button>
      </div>
    </div>
  );
}

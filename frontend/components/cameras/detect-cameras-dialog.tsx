"use client";

/**
 * Auto-discovery dialog for the Cameras page.
 *
 * Triggers a backend ONVIF WS-Discovery multicast + TCP scan of local
 * /24 subnets. Lists every camera found with vendor hint. Each row has
 * a "Connect" button that opens Smart Connect with the IP pre-filled,
 * so the operator only types credentials and clicks Save.
 */

import {
  Camera as CameraIcon,
  CheckCircle2,
  Loader2,
  Radar,
  Wifi,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { camerasApi } from "@/lib/api/cameras";

interface DiscoveredCamera {
  ip: string;
  source: "onvif" | "tcp_scan";
  onvif_url: string | null;
  rtsp_port: number;
  web_port: number;
  vendor_hint: string | null;
  notes: string[];
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-fill Smart Connect wizard with this IP. */
  onConnectClick: (cam: DiscoveredCamera) => void;
}

export function DetectCamerasDialog({
  open,
  onOpenChange,
  onConnectClick,
}: Props) {
  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<DiscoveredCamera[] | null>(null);

  async function runScan() {
    setScanning(true);
    setResults(null);
    try {
      const res = await camerasApi.discover();
      setResults(res.cameras);
      if (res.count === 0) {
        toast.warning(
          "No cameras found. Check that the camera's Ethernet cable is plugged into the PoE switch + this PC.",
        );
      } else {
        toast.success(`Found ${res.count} device${res.count > 1 ? "s" : ""}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Scan failed");
      setResults([]);
    } finally {
      setScanning(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Radar className="h-5 w-5 text-primary" />
            Detect cameras on this network
          </DialogTitle>
          <DialogDescription>
            Multicast ONVIF probe + TCP scan of local subnets. Discovery never
            saves anything — click a result to launch Smart Connect with the
            IP pre-filled.
          </DialogDescription>
        </DialogHeader>

        <div className="flex justify-center">
          <Button
            size="lg"
            onClick={runScan}
            disabled={scanning}
            className="min-w-[200px]"
          >
            {scanning ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Scanning (up to ~30 seconds)…
              </>
            ) : (
              <>
                <Wifi className="h-4 w-4" />
                {results === null ? "Start scan" : "Scan again"}
              </>
            )}
          </Button>
        </div>

        {results !== null && (
          <div className="space-y-2 rounded-md border bg-muted/20 p-3">
            {results.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground">
                No devices responded. Try:
                <br />
                · plug the camera into the same PoE switch as this PC
                <br />
                · ensure the PC has a static IP on the camera subnet
                <br />
                · check Windows Firewall isn&apos;t blocking outbound UDP 3702
              </p>
            ) : (
              results.map((cam) => (
                <div
                  key={cam.ip}
                  className="flex items-center justify-between gap-3 rounded-md border bg-card p-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <CameraIcon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="font-mono text-sm font-semibold">
                          {cam.ip}
                        </code>
                        {cam.vendor_hint && (
                          <Badge variant="secondary" className="text-[10px]">
                            {cam.vendor_hint}
                          </Badge>
                        )}
                        <Badge
                          variant={cam.source === "onvif" ? "default" : "outline"}
                          className="text-[10px]"
                        >
                          {cam.source === "onvif" ? (
                            <>
                              <CheckCircle2 className="mr-0.5 h-2.5 w-2.5" />
                              ONVIF
                            </>
                          ) : (
                            "Port 554"
                          )}
                        </Badge>
                      </div>
                      <p className="truncate text-xs text-muted-foreground">
                        {cam.onvif_url ?? cam.notes.join(" · ")}
                      </p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => {
                      onConnectClick(cam);
                      onOpenChange(false);
                    }}
                  >
                    Connect →
                  </Button>
                </div>
              ))
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

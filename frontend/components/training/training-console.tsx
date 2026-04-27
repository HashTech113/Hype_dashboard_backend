"use client";

import { Camera as CameraIcon, Loader2, ScanFace } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CameraPicker } from "@/components/training/camera-picker";
import { EmployeePicker } from "@/components/training/employee-picker";
import { FaceImageGallery } from "@/components/training/face-image-gallery";
import { ImageDropzone } from "@/components/training/image-dropzone";
import { TrainingResultPanel } from "@/components/training/training-result-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useCaptureFromCamera,
  useFaceImages,
  useUploadImages,
} from "@/lib/hooks/use-training";
import type { Employee } from "@/lib/types/employee";
import type { TrainingResult } from "@/lib/types/training";

const MIN_IMAGES = 5;
const MAX_IMAGES = 20;

interface Props {
  initialEmployee?: Employee | null;
}

export function TrainingConsole({ initialEmployee = null }: Props) {
  const [employee, setEmployee] = useState<Employee | null>(initialEmployee);
  const [cameraId, setCameraId] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<TrainingResult | null>(null);

  const uploadMut = useUploadImages();
  const captureMut = useCaptureFromCamera();
  const imagesQuery = useFaceImages(employee?.id ?? null);

  const enrolled = imagesQuery.data?.length ?? 0;
  const remaining = MAX_IMAGES - enrolled;

  function handleUpload(files: File[], replace: boolean) {
    if (!employee) return;
    uploadMut.mutate(
      { employeeId: employee.id, files, replace },
      { onSuccess: (res) => setLastResult(res) },
    );
  }

  function handleCapture() {
    if (!employee || !cameraId) return;
    captureMut.mutate(
      { employeeId: employee.id, cameraId },
      { onSuccess: (res) => setLastResult(res) },
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[340px,_1fr]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle className="text-base">Employee</CardTitle>
          <CardDescription>Pick whom you want to enroll.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <EmployeePicker value={employee} onChange={(e) => setEmployee(e)} />

          {employee && (
            <div className="space-y-2 rounded-md border bg-muted/10 p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Code</span>
                <span className="font-medium">{employee.employee_code}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Department</span>
                <span className="font-medium">{employee.department || "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Enrolled images</span>
                {imagesQuery.isLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                ) : (
                  <Badge
                    variant={
                      enrolled >= MIN_IMAGES ? "success" : "warning"
                    }
                  >
                    {enrolled} / {MAX_IMAGES}
                  </Badge>
                )}
              </div>
              {enrolled < MIN_IMAGES && (
                <p className="pt-1 text-xs text-warning">
                  Needs at least {MIN_IMAGES} images for recognition.
                </p>
              )}
              {enrolled >= MAX_IMAGES && (
                <p className="pt-1 text-xs text-muted-foreground">
                  Maximum reached. Remove one below to add more.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Enroll faces</CardTitle>
            <CardDescription>
              Upload images or capture directly from a running camera.
              Recommended: {MIN_IMAGES}–{MAX_IMAGES} images per employee, from
              different angles and lighting.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!employee ? (
              <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed py-10 text-sm text-muted-foreground">
                <ScanFace className="h-5 w-5" />
                Select an employee to start enrollment.
              </div>
            ) : (
              <Tabs defaultValue="upload">
                <TabsList>
                  <TabsTrigger value="upload">Upload images</TabsTrigger>
                  <TabsTrigger value="capture">Live capture</TabsTrigger>
                </TabsList>

                <TabsContent value="upload" className="mt-4">
                  <ImageDropzone
                    min={Math.max(1, MIN_IMAGES - Math.min(enrolled, MIN_IMAGES))}
                    max={Math.max(1, remaining)}
                    submitting={uploadMut.isPending}
                    onSubmit={handleUpload}
                    disabled={enrolled >= MAX_IMAGES}
                  />
                </TabsContent>

                <TabsContent value="capture" className="mt-4 space-y-4">
                  <div className="grid gap-2">
                    <p className="text-sm font-medium">Camera</p>
                    <CameraPicker
                      value={cameraId}
                      onChange={setCameraId}
                      disabled={captureMut.isPending}
                    />
                    <p className="text-xs text-muted-foreground">
                      The latest in-memory frame from the selected camera will
                      be captured. Make sure the employee is clearly visible.
                    </p>
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      disabled={
                        !cameraId ||
                        captureMut.isPending ||
                        enrolled >= MAX_IMAGES
                      }
                      onClick={() => {
                        if (enrolled >= MAX_IMAGES) {
                          toast.error("Maximum images reached");
                          return;
                        }
                        handleCapture();
                      }}
                    >
                      {captureMut.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <CameraIcon className="h-4 w-4" />
                      )}
                      {captureMut.isPending ? "Capturing…" : "Capture now"}
                    </Button>
                  </div>
                </TabsContent>
              </Tabs>
            )}

            {lastResult && (
              <div className="mt-6">
                <TrainingResultPanel result={lastResult} />
              </div>
            )}
          </CardContent>
        </Card>

        {employee && (
          <Card>
            <CardHeader>
              <CardTitle>Enrolled images</CardTitle>
              <CardDescription>
                {enrolled} image{enrolled === 1 ? "" : "s"} on file for{" "}
                {employee.name}. Remove an image to re-enroll with a better one.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FaceImageGallery employeeId={employee.id} />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

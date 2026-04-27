import { api } from "@/lib/api/client";
import type { Page } from "@/lib/types/common";
import type {
  PromoteResponse,
  PromoteToNewPayload,
  PurgeResponse,
  ReclusterResponse,
  UnknownCluster,
  UnknownClusterDetail,
  UnknownClusterListParams,
} from "@/lib/types/unknowns";

export const unknownsApi = {
  list: (params: UnknownClusterListParams = {}) =>
    api.get<Page<UnknownCluster>>("/unknowns/clusters", {
      params: {
        status: params.status,
        label: params.label,
        limit: params.limit,
        offset: params.offset,
      },
    }),

  get: (clusterId: number) =>
    api.get<UnknownClusterDetail>(`/unknowns/clusters/${clusterId}`),

  captureBlob: (captureId: number) =>
    api.get<Blob>(`/unknowns/captures/${captureId}/image`, {
      responseType: "blob",
    }),

  setLabel: (clusterId: number, label: string | null) =>
    api.patch<UnknownCluster>(`/unknowns/clusters/${clusterId}`, { label }),

  discard: (clusterId: number) =>
    api.delete<void>(`/unknowns/clusters/${clusterId}`),

  promoteNew: (clusterId: number, payload: PromoteToNewPayload) =>
    api.post<PromoteResponse>(
      `/unknowns/clusters/${clusterId}/promote/new`,
      payload,
    ),

  promoteExisting: (clusterId: number, employeeId: number) =>
    api.post<PromoteResponse>(
      `/unknowns/clusters/${clusterId}/promote/existing/${employeeId}`,
    ),

  recluster: (params: { min_cluster_size?: number; min_samples?: number } = {}) =>
    api.post<ReclusterResponse>("/unknowns/recluster", {
      min_cluster_size: params.min_cluster_size ?? 2,
      min_samples: params.min_samples ?? 1,
    }),

  purge: (params: { max_age_days?: number | null; include_promoted?: boolean } = {}) =>
    api.post<PurgeResponse>("/unknowns/purge", {
      max_age_days: params.max_age_days ?? null,
      include_promoted: params.include_promoted ?? false,
    }),
};

import axios, {
  AxiosError,
  AxiosHeaders,
  AxiosInstance,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from "axios";

import { clearToken, getToken } from "@/lib/auth/session";

export class ApiError extends Error {
  status: number;
  code: string;
  data: unknown;
  constructor(status: number, code: string, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

export interface RequestOptions {
  params?: Record<string, string | number | boolean | undefined | null>;
  headers?: Record<string, string>;
  auth?: boolean;
  signal?: AbortSignal;
  responseType?: "json" | "blob";
  timeout?: number;
}

function baseURL(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured");
  }
  return url.replace(/\/$/, "");
}

const DEFAULT_TIMEOUT_MS = 20_000;

function buildClient(): AxiosInstance {
  const instance = axios.create({
    baseURL: baseURL(),
    timeout: DEFAULT_TIMEOUT_MS,
    headers: { Accept: "application/json" },
  });

  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const auth = (config as { __auth?: boolean }).__auth;
    if (auth !== false) {
      const token = getToken();
      if (token) {
        const headers = AxiosHeaders.from(config.headers);
        headers.set("Authorization", `Bearer ${token}`);
        config.headers = headers;
      }
    }
    return config;
  });

  instance.interceptors.response.use(
    (r: AxiosResponse) => r,
    (error: AxiosError) => {
      if (error.response?.status === 401) {
        const authRequired = (error.config as { __auth?: boolean } | undefined)?.__auth !== false;
        if (authRequired) clearToken();
      }
      return Promise.reject(toApiError(error));
    },
  );

  return instance;
}

function toApiError(error: AxiosError): ApiError {
  if (error.response) {
    const status = error.response.status;
    const body = error.response.data as
      | { error?: string; message?: string; detail?: unknown }
      | undefined;
    const code = body?.error ?? `http_${status}`;
    const message =
      body?.message ??
      (typeof body?.detail === "string" ? body.detail : error.response.statusText) ??
      "Request failed";
    return new ApiError(status, code, message, body);
  }
  if (error.code === "ECONNABORTED") {
    return new ApiError(0, "timeout", "Request timed out");
  }
  return new ApiError(0, "network_error", error.message || "Network error");
}

let _client: AxiosInstance | null = null;
function client(): AxiosInstance {
  if (_client === null) _client = buildClient();
  return _client;
}

interface InternalConfig {
  method: "get" | "post" | "patch" | "put" | "delete";
  path: string;
  body?: unknown;
  options?: RequestOptions;
}

async function request<T>({ method, path, body, options }: InternalConfig): Promise<T> {
  const res = await client().request<T>({
    method,
    url: path.startsWith("/") ? path : `/${path}`,
    params: options?.params,
    headers: options?.headers,
    data: body,
    signal: options?.signal,
    responseType: options?.responseType ?? "json",
    timeout: options?.timeout ?? DEFAULT_TIMEOUT_MS,
    // carry our auth flag through to interceptor without polluting axios typings
    ...(options?.auth === false ? { __auth: false as const } : {}),
  } as InternalAxiosRequestConfig & { __auth?: boolean });
  if (res.status === 204) return undefined as T;
  return res.data as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>({ method: "get", path, options }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>({ method: "post", path, body, options }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>({ method: "patch", path, body, options }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>({ method: "put", path, body, options }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>({ method: "delete", path, options }),
};

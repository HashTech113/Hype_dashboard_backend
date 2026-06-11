import { QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";

let _client: QueryClient | null = null;

export function createQueryClient(): QueryClient {
  // Reuse the singleton if it was already created (e.g. by providers.tsx).
  // The 401 interceptor in lib/api/client.ts calls getQueryClient().clear()
  // — it must hit the same instance the hooks are using.
  if (_client !== null) return _client;
  _client = new QueryClient({
    // H11 fix (part 2): global QueryCache.onError so failures the page-
    // level component DIDN'T handle still surface somewhere instead of
    // being silent. A page that handles isError locally suppresses this
    // (the toast still fires, but the page already shows an inline error
    // — that's OK as a "loud + redundant" signal).
    queryCache: new QueryCache({
      onError: (error, query) => {
        // 401 is handled by the axios interceptor (clears cache + redirects).
        // Don't double-toast or scare the user during the redirect.
        if (error instanceof ApiError && error.status === 401) return;
        // 503 is the new "DB temporarily down" — separate toast text.
        if (error instanceof ApiError && error.status === 503) {
          toast.warning("Backend temporarily unavailable — retrying...", {
            id: "backend-down",
          });
          return;
        }
        // Only toast queries that have actually been rendered. Background
        // hydration of an unused query shouldn't pop a toast.
        if (query.state.fetchStatus === "fetching" && (query.state.data === undefined)) {
          const msg =
            error instanceof ApiError ? error.message : "A request failed.";
          // De-dupe rapid repeats — TanStack retries before this lands.
          toast.error(msg, { id: `qry:${query.queryHash}` });
        }
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
  return _client;
}

export function getQueryClient(): QueryClient {
  if (_client === null) _client = createQueryClient();
  return _client;
}

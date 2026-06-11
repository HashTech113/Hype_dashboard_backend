"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect, useState } from "react";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth/context";
import { createQueryClient } from "@/lib/query-client";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  // H12 fix: when a blob-cache entry is garbage-collected (after gcTime),
  // revoke the ObjectURL so the browser frees the underlying blob memory.
  // Without this, every fetched face image leaks ~50 KB of blob memory
  // for the lifetime of the tab.
  useEffect(() => {
    const cache = queryClient.getQueryCache();
    const unsubscribe = cache.subscribe((event) => {
      if (event.type !== "removed") return;
      const data = event.query.state.data;
      if (typeof data === "string" && data.startsWith("blob:")) {
        try {
          URL.revokeObjectURL(data);
        } catch {
          /* ignore */
        }
      }
    });
    return unsubscribe;
  }, [queryClient]);

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          {children}
          <Toaster richColors position="top-right" closeButton />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

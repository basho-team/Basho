"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { DataSourceError } from "@/lib/data/source";

const DEFAULT_STALE_TIME_MS = 60_000;
const MAX_QUERY_RETRIES = 2;

/** Erros estruturados marcados como não recuperáveis aparecem na hora, sem novas tentativas. */
function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof DataSourceError && !error.error.retryable) return false;
  return failureCount < MAX_QUERY_RETRIES;
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: DEFAULT_STALE_TIME_MS, retry: shouldRetry },
    },
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

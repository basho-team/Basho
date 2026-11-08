"use client";

import { useQuery } from "@tanstack/react-query";

import { periodQuery } from "@/components/basho/hooks";
import { api } from "@/lib/api";
import type { DemoContext, ReportVersionOut } from "@/lib/types";

export function useReports(ctx: DemoContext) {
  return useQuery({
    queryKey: ["reports", ctx.project_id],
    queryFn: () => api.get<ReportVersionOut[]>(`projects/${ctx.project_id}/reports?${periodQuery(ctx)}`),
  });
}

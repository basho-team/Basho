"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { DemoContext } from "@/lib/types";

export function useDemoContext() {
  return useQuery({ queryKey: ["context"], queryFn: () => api.get<DemoContext>("demo/context") });
}

export function periodQuery(ctx: DemoContext): string {
  const p = ctx.period;
  return new URLSearchParams({ start: p.start, end: p.end, timezone: p.timezone, periodicity: p.periodicity }).toString();
}

export function personName(ctx: DemoContext | undefined, id: string): string {
  return ctx?.people.find((p) => p.id === id)?.name ?? `pessoa ${id.slice(0, 8)}`;
}

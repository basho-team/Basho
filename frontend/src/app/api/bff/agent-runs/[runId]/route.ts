import type { NextRequest } from "next/server";
import { getRun } from "@/lib/server/integrations-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/agent-runs/[runId]">) {
  const { runId } = await ctx.params;
  return getRun(runId, request);
}

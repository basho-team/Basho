import type { NextRequest } from "next/server";
import { getSources } from "@/lib/server/integrations-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/sources">) {
  const { projectId } = await ctx.params;
  return getSources(projectId, request);
}

import type { NextRequest } from "next/server";
import { listPublications, postPublish } from "@/lib/server/integrations-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/publications">) {
  const { projectId } = await ctx.params;
  return listPublications(projectId, request);
}

export async function POST(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/publications">) {
  const { projectId } = await ctx.params;
  return postPublish(projectId, request);
}

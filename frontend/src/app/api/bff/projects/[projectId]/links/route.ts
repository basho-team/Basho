import type { NextRequest } from "next/server";
import { listLinks, postLink } from "@/lib/server/integrations-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/links">) {
  const { projectId } = await ctx.params;
  return listLinks(projectId, request);
}

export async function POST(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/links">) {
  const { projectId } = await ctx.params;
  return postLink(projectId, request);
}

import type { NextRequest } from "next/server";
import { getProject } from "@/lib/server/projects-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]">) {
  const { projectId } = await ctx.params;
  return getProject(projectId, request);
}

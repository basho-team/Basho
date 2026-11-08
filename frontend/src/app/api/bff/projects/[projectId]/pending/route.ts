import type { NextRequest } from "next/server";
import { listPending } from "@/lib/server/projects-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/pending">) {
  const { projectId } = await ctx.params;
  return listPending(projectId, request);
}

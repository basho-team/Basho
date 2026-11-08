import type { NextRequest } from "next/server";
import { postGenerate } from "@/lib/server/integrations-bff";

export async function POST(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/generate">) {
  const { projectId } = await ctx.params;
  return postGenerate(projectId, request);
}

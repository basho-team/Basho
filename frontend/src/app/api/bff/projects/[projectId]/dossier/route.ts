import type { NextRequest } from "next/server";
import { getDossier } from "@/lib/server/projects-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/dossier">) {
  const { projectId } = await ctx.params;
  return getDossier(projectId, request);
}

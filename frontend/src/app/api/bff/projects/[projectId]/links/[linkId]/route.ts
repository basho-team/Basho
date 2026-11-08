import type { NextRequest } from "next/server";
import { deleteLink } from "@/lib/server/integrations-bff";

export async function DELETE(request: NextRequest, ctx: RouteContext<"/api/bff/projects/[projectId]/links/[linkId]">) {
  const { projectId, linkId } = await ctx.params;
  return deleteLink(projectId, linkId, request);
}

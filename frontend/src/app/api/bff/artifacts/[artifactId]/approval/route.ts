import type { NextRequest } from "next/server";
import { postApproval } from "@/lib/server/projects-bff";

export async function POST(request: NextRequest, ctx: RouteContext<"/api/bff/artifacts/[artifactId]/approval">) {
  const { artifactId } = await ctx.params;
  return postApproval(artifactId, request);
}

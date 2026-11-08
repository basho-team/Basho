import type { NextRequest } from "next/server";
import { postReview } from "@/lib/server/reports-bff";

export async function POST(request: NextRequest, ctx: RouteContext<"/api/bff/reports/[versionId]/review">) {
  const { versionId } = await ctx.params;
  return postReview(versionId, request);
}

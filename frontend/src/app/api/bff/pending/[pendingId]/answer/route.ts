import type { NextRequest } from "next/server";
import { postAnswer } from "@/lib/server/projects-bff";

export async function POST(request: NextRequest, ctx: RouteContext<"/api/bff/pending/[pendingId]/answer">) {
  const { pendingId } = await ctx.params;
  return postAnswer(pendingId, request);
}

import type { NextRequest } from "next/server";
import { getReportVersion } from "@/lib/server/reports-bff";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/reports/[versionId]">) {
  const { versionId } = await ctx.params;
  return getReportVersion(versionId, request);
}

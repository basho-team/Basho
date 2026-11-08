import type { NextRequest } from "next/server";
import { getConfig } from "@/lib/server/integrations-bff";

export async function GET(request: NextRequest) {
  return getConfig(request);
}

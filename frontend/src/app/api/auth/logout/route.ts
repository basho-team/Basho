import { NextResponse } from "next/server";
import { authError, sameOriginJson, SESSION_COOKIE, publicOrigin, sessionStore, sessionToken } from "@/lib/auth/session";

export async function POST(request: Request): Promise<Response> {
  if (!sameOriginJson(request)) return authError(403, "Origem da solicitação recusada.");
  await sessionStore().destroy(sessionToken(request));
  const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0,
    secure: publicOrigin(request).startsWith("https:") });
  return response;
}

import { boundedJson } from "@/lib/auth/http";
import { NextResponse } from "next/server";
import { LoginSchema, authenticateDemo, consumeLoginAttempt } from "@/lib/auth/login";
import { authError, createSession, demoLoginEnabled, hasDemoPassword, sameOriginJson, SESSION_COOKIE,
  SESSION_TTL_SECONDS, sessionStore, sessionToken, publicOrigin } from "@/lib/auth/session";

export async function POST(request: Request): Promise<Response> {
  if (!sameOriginJson(request)) return authError(403, "Origem da solicitação recusada.");
  if (!demoLoginEnabled() || !hasDemoPassword()) return authError(503, "Login de demonstração não configurado.");
  const body = await boundedJson(request, 4096);
  if (body instanceof Response) return body;
  const parsed = LoginSchema.safeParse(body);
  if (!parsed.success) return authError(400, "Confira e-mail, senha e função.");
  if (!consumeLoginAttempt(parsed.data.email)) return authError(429, "Muitas tentativas. Tente novamente em 15 minutos.");
  const accountId = await authenticateDemo(parsed.data);
  if (!accountId) return authError(401, "E-mail, senha ou função não autorizados.");
  await sessionStore().destroy(sessionToken(request));
  const token = await createSession(accountId);
  const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true, sameSite: "lax", path: "/", maxAge: SESSION_TTL_SECONDS,
    secure: publicOrigin(request).startsWith("https:"),
  });
  return response;
}

import { NextResponse } from "next/server";
import { z } from "zod";
import { boundedJson } from "@/lib/auth/http";
import { DEMO_ACCOUNTS } from "@/lib/auth/shared";
import { authError, createSession, openAccessEnabled, sameOriginJson, SESSION_COOKIE,
  SESSION_TTL_SECONDS, sessionSecret } from "@/lib/auth/session";

const BodySchema = z.object({ accountId: z.string().max(40) }).strict();

/**
 * Entrada rápida da demonstração: um clique na conta cria a sessão, sem senha. Só existe com
 * `BASHO_DEMO_OPEN_ACCESS=true` (desligada por padrão) e para as contas fictícias do cadastro.
 */
export async function POST(request: Request): Promise<Response> {
  if (!openAccessEnabled()) return authError(404, "Entrada rápida desativada neste ambiente.");
  if (!sameOriginJson(request)) return authError(403, "Origem da solicitação recusada.");
  const body = await boundedJson(request, 1024);
  if (body instanceof Response) return body;
  const parsed = BodySchema.safeParse(body);
  const account = parsed.success ? DEMO_ACCOUNTS.find(candidate => candidate.id === parsed.data.accountId) : undefined;
  if (!account) return authError(400, "Conta de demonstração desconhecida.");
  if (!sessionSecret() && process.env.VERCEL) {
    return authError(503, "Defina BASHO_DEMO_SESSION_SECRET (32 caracteres ou mais) neste ambiente.");
  }
  let token: string;
  try { token = await createSession(account.id); } catch {
    return authError(503, "Não foi possível iniciar a sessão neste ambiente.");
  }
  const response = NextResponse.json({ ok: true, role: account.role }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true, sameSite: "lax", path: "/", maxAge: SESSION_TTL_SECONDS,
    secure: new URL(request.url).protocol === "https:",
  });
  return response;
}

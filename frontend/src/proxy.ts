import { NextResponse, type NextRequest } from "next/server";

import { mayVisit } from "@/lib/auth/shared";
import { userFromRequest } from "@/lib/auth/session";
import { checkBasicAuth } from "@/lib/server/basic-auth";

/**
 * Duas camadas, nesta ordem (uma não substitui a outra — handoff do login, #67/#68):
 *
 * 1. Portão do deploy (Basic Auth, DEMO_BASIC_AUTH_USER/PASSWORD, só servidor). Em modo
 *    `api` sem credenciais configuradas, o site fica fechado (503). Em modo `mock` sem
 *    credenciais, o portão fica aberto.
 * 2. Sessão individual por função (login local da demonstração, ADR-0011 proposta).
 */
const SESSION_PREFIXES = ["/pesquisador", "/gerente", "/fiscal", "/integracoes", "/api/"] as const;
const SESSION_EXACT = ["/", "/login", "/acesso-negado"] as const;

function needsSession(pathname: string): boolean {
  return (
    (SESSION_EXACT as readonly string[]).includes(pathname) ||
    SESSION_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`))
  );
}

function deployGate(request: NextRequest): NextResponse | null {
  const result = checkBasicAuth(request.headers.get("authorization"), {
    dataSource: process.env.NEXT_PUBLIC_DATA_SOURCE,
    user: process.env.DEMO_BASIC_AUTH_USER,
    password: process.env.DEMO_BASIC_AUTH_PASSWORD,
  });
  if (result === "allow") return null;
  if (result === "misconfigured") {
    return new NextResponse("Acesso indisponível: credenciais da demo não configuradas.", {
      status: 503,
    });
  }
  return new NextResponse("Autenticação necessária.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Basho demo", charset="UTF-8"' },
  });
}

async function sessionGate(request: NextRequest): Promise<NextResponse> {
  const pathname = request.nextUrl.pathname;
  const user = await userFromRequest(request);
  const publicAuth = pathname === "/login" || pathname.startsWith("/api/auth/");
  if (publicAuth) {
    if (pathname === "/login" && user) return NextResponse.redirect(new URL("/", request.url));
    return NextResponse.next();
  }
  if (!user) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ message: "Entre para continuar." }, { status: 401,
        headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (!pathname.startsWith("/api/") && !mayVisit(user.role, pathname)) {
    return NextResponse.redirect(new URL("/acesso-negado", request.url));
  }
  const response = NextResponse.next();
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const blocked = deployGate(request);
  if (blocked) return blocked;
  if (!needsSession(request.nextUrl.pathname)) return NextResponse.next();
  return sessionGate(request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|ico|webp)$).*)"],
};

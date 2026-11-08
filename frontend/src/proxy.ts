import { NextResponse, type NextRequest } from "next/server";

import { checkBasicAuth } from "@/lib/server/basic-auth";

/**
 * Camada de acesso do deploy público (placeholder até a autenticação real, #47).
 *
 * O BFF repassa a identidade do revisor sem autenticar ninguém; por isso, em modo `api`,
 * o site só abre com Basic Auth (DEMO_BASIC_AUTH_USER/PASSWORD, só servidor). Sem as
 * credenciais configuradas, o modo `api` fica fechado (503) em vez de aberto.
 */
export function proxy(request: NextRequest): NextResponse {
  const result = checkBasicAuth(request.headers.get("authorization"), {
    dataSource: process.env.NEXT_PUBLIC_DATA_SOURCE,
    user: process.env.DEMO_BASIC_AUTH_USER,
    password: process.env.DEMO_BASIC_AUTH_PASSWORD,
  });
  if (result === "allow") return NextResponse.next();
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

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|ico|webp)$).*)"],
};

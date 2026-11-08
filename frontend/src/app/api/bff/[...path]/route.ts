import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { PERSONA_COOKIE, parsePersona } from "@/lib/persona";
import { serverEnv } from "@/lib/server/env";

/**
 * BFF: repassa à API do Basho só os caminhos da jornada e, se houver persona de demonstração,
 * acrescenta a identidade afirmada e o segredo server-to-server (REVIEWER_IDENTITY_SECRET).
 * O segredo nunca chega ao navegador. Identidade é de demonstração (sem autenticação real, #47).
 */
const ALLOWED = /^(demo\/context|projects\/[0-9a-f-]{36}\/(evidence|reports|consolidation|dossier)|reports(\/[0-9a-f-]{36}(\/(history|checks|review))?)?)$/;

async function forward(request: NextRequest, path: string[]): Promise<NextResponse> {
  const joined = path.join("/");
  if (!ALLOWED.test(joined)) {
    return NextResponse.json({ detail: "rota não permitida pelo BFF" }, { status: 404 });
  }
  const url = new URL(`/api/v1/${joined}`, serverEnv.BASHO_API_URL);
  url.search = request.nextUrl.search;
  const headers = new Headers({ accept: "application/json" });
  const persona = parsePersona((await cookies()).get(PERSONA_COOKIE)?.value);
  if (persona && serverEnv.REVIEWER_IDENTITY_SECRET) {
    headers.set("X-Basho-User-Id", persona.userId);
    headers.set("X-Basho-Role", persona.role);
    headers.set("X-Basho-Identity-Secret", serverEnv.REVIEWER_IDENTITY_SECRET);
  }
  let body: string | undefined;
  if (request.method !== "GET") {
    body = await request.text();
    headers.set("content-type", "application/json");
  }
  try {
    const upstream = await fetch(url, { method: request.method, headers, body, cache: "no-store" });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "API do Basho inacessível. Verifique se o backend está rodando." },
      { status: 502 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  return forward(request, (await ctx.params).path);
}

export async function POST(request: NextRequest, ctx: Ctx) {
  return forward(request, (await ctx.params).path);
}

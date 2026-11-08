import { NextRequest } from "next/server";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SignedSessionStore } from "@/lib/auth/session";
import { proxy } from "@/proxy";

const SECRET = "s".repeat(40);
const BASIC = `Basic ${btoa("juri:senha-forte")}`;

function request(path: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(new URL(path, "https://basho.example"), { headers });
}

afterEach(() => vi.unstubAllEnvs());

describe("proxy: portão do deploy + sessão individual", () => {
  test("modo api sem credenciais de deploy fica fechado", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "api");

    expect((await proxy(request("/"))).status).toBe(503);
  });

  test("modo api com credenciais exige Basic Auth antes da sessão", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "api");
    vi.stubEnv("DEMO_BASIC_AUTH_USER", "juri");
    vi.stubEnv("DEMO_BASIC_AUTH_PASSWORD", "senha-forte");

    expect((await proxy(request("/gerente"))).status).toBe(401);
    const passed = await proxy(request("/gerente", { authorization: BASIC }));
    expect(passed.status).toBe(307);
    expect(passed.headers.get("location")).toContain("/login");
  });

  test("com Basic Auth válido, a sessão ainda decide a função", async () => {
    vi.stubEnv("DEMO_BASIC_AUTH_USER", "juri");
    vi.stubEnv("DEMO_BASIC_AUTH_PASSWORD", "senha-forte");
    vi.stubEnv("BASHO_DEMO_LOGIN_ENABLED", "true");
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
    const token = await new SignedSessionStore(SECRET).create("ana");
    const headers = { authorization: BASIC, cookie: `basho_demo_session=${token}` };

    expect((await proxy(request("/pesquisador", headers))).status).toBe(200);
    const denied = await proxy(request("/gerente", headers));
    expect(denied.headers.get("location")).toContain("/acesso-negado");
  });

  test("modo mock sem credenciais de deploy ainda exige login nas páginas", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "mock");

    const response = await proxy(request("/fiscal"));
    expect(response.headers.get("location")).toContain("/login");
    expect((await proxy(request("/login"))).status).toBe(200);
  });
});

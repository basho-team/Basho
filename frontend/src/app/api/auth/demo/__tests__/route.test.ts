import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { userFromRequest } from "@/lib/auth/session";
import { POST } from "../route";

const SECRET = "s".repeat(40);
const ORIGIN = "http://localhost:3000";

function request(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`${ORIGIN}/api/auth/demo`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", Origin: ORIGIN, ...headers },
  });
}

beforeEach(() => {
  vi.stubEnv("BASHO_DEMO_OPEN_ACCESS", "true");
  vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
});
afterEach(() => vi.unstubAllEnvs());

describe("POST /api/auth/demo (entrada rápida)", () => {
  test("desligada por padrão: nem existe", async () => {
    vi.stubEnv("BASHO_DEMO_OPEN_ACCESS", "false");
    expect((await POST(request({ accountId: "marina" }))).status).toBe(404);
  });

  test("um clique na conta cria a sessão com a função da conta", async () => {
    // Act
    const res = await POST(request({ accountId: "marina" }));

    // Assert
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, role: "manager" });
    const cookie = res.headers.get("set-cookie") ?? "";
    expect(cookie).toMatch(/basho_demo_session=s1\./);
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie.toLowerCase()).toContain("samesite=lax");
    expect(cookie.toLowerCase()).not.toContain("secure"); // http local
    const token = /basho_demo_session=([^;]+)/.exec(cookie)?.[1] ?? "";
    const user = await userFromRequest(new Request(`${ORIGIN}/x`, { headers: { cookie: `basho_demo_session=${token}` } }));
    expect(user).toMatchObject({ accountId: "marina", role: "manager" });
  });

  test("em https o cookie é Secure", async () => {
    const secure = new Request("https://demo.example/api/auth/demo", {
      method: "POST",
      body: JSON.stringify({ accountId: "ana" }),
      headers: { "Content-Type": "application/json", Origin: "https://demo.example" },
    });
    expect((await POST(secure)).headers.get("set-cookie")?.toLowerCase()).toContain("secure");
  });

  test.each([
    ["conta desconhecida", { accountId: "intruso" }],
    ["campo extra (papel escolhido pelo cliente)", { accountId: "ana", role: "manager" }],
    ["sem conta", {}],
  ])("recusa %s", async (_name, body) => {
    expect((await POST(request(body))).status).toBe(400);
  });

  test("recusa outra origem (CSRF)", async () => {
    expect((await POST(request({ accountId: "ana" }, { Origin: "http://evil.example" }))).status).toBe(403);
  });

  test("recusa corpo que não é JSON", async () => {
    expect((await POST(request({ accountId: "ana" }, { "Content-Type": "text/plain" }))).status).toBe(403);
  });

  test("na Vercel sem segredo de sessão avisa o que configurar, em vez de falhar no disco", async () => {
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", "");
    vi.stubEnv("VERCEL", "1");
    const res = await POST(request({ accountId: "ana" }));
    expect(res.status).toBe(503);
    expect((await res.json()).message).toContain("BASHO_DEMO_SESSION_SECRET");
  });
});

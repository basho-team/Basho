import { afterEach, describe, expect, test, vi } from "vitest";
import { readSignedSession, sessionSecret, signSession, SESSION_TTL_SECONDS, userFromRequest, userFromToken } from "../session";

const SECRET = "s".repeat(40);
const OTHER = "o".repeat(40);
const NOW = 1_000_000;
const MARINA_UUID = "55555555-5555-4555-8555-555555555555";

afterEach(() => vi.unstubAllEnvs());

describe("sessão assinada (sem disco)", () => {
  test("round-trip: a conta define a função", () => {
    // Arrange
    const token = signSession("marina", SECRET, NOW);

    // Act
    const user = readSignedSession(token, SECRET, NOW + 1000);

    // Assert
    expect(token.startsWith("s1.")).toBe(true);
    expect(user).toMatchObject({ accountId: "marina", role: "manager", personId: "p-marina" });
  });

  test("segredo errado ou ausente não concede acesso", () => {
    const token = signSession("marina", SECRET, NOW);
    expect(readSignedSession(token, OTHER, NOW)).toBeNull();
    expect(readSignedSession(token, null, NOW)).toBeNull();
  });

  test("payload adulterado (troca de conta para promover a função) é recusado", () => {
    // Arrange: ana (pesquisadora) tenta virar marina (gerente) mantendo a assinatura
    const [prefixAndPayload, mac] = signSession("ana", SECRET, NOW).split(".").slice(1);
    const forged = Buffer.from(JSON.stringify({ a: "marina", i: NOW, e: NOW + SESSION_TTL_SECONDS * 1000 })).toString("base64url");

    // Act / Assert
    expect(prefixAndPayload).toBeTruthy();
    expect(readSignedSession(`s1.${forged}.${mac}`, SECRET, NOW)).toBeNull();
  });

  test.each([
    ["expirada", NOW + SESSION_TTL_SECONDS * 1000 + 1],
    ["no futuro (relógio adulterado)", NOW - 1],
  ])("sessão %s não vale", (_name, readAt) => {
    expect(readSignedSession(signSession("ana", SECRET, NOW), SECRET, readAt)).toBeNull();
  });

  test.each(["", "s1.", "s1.a.b.c", "s1.só-um-pedaço", "x".repeat(600), "0".repeat(64)])("lixo %j é recusado", token => {
    expect(readSignedSession(token, SECRET, NOW)).toBeNull();
  });

  test("conta inexistente não gera token", () => {
    expect(() => signSession("intruso", SECRET, NOW)).toThrow();
  });

  test("segredo curto é ignorado (não vira sessão assinada)", () => {
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", "curto");
    expect(sessionSecret()).toBeNull();
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
    expect(sessionSecret()).toBe(SECRET);
  });

  test("o UUID do backend vem do mapeamento do servidor", () => {
    vi.stubEnv("BASHO_DEMO_BACKEND_USERS", JSON.stringify({ marina: MARINA_UUID }));
    expect(readSignedSession(signSession("marina", SECRET, NOW), SECRET, NOW)?.backendUserId).toBe(MARINA_UUID);
  });
});

describe("userFromRequest com sessão assinada", () => {
  const request = (token: string) => new Request("http://localhost/x", { headers: { cookie: `basho_demo_session=${token}` } });

  test("vale quando a entrada rápida está ligada e há segredo", async () => {
    vi.stubEnv("BASHO_DEMO_OPEN_ACCESS", "true");
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
    const token = signSession("rafael", SECRET);
    expect(await userFromRequest(request(token))).toMatchObject({ role: "fiscal" });
  });

  test("não vale com o login desligado", async () => {
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
    expect(await userFromRequest(request(signSession("rafael", SECRET)))).toBeNull();
  });
});

describe("userFromToken (caminho único: proxy, rotas e layout)", () => {
  test("o layout aceita a sessão assinada; antes ele só lia arquivo e entrava em laço de redirecionamento", async () => {
    // Arrange
    vi.stubEnv("BASHO_DEMO_OPEN_ACCESS", "true");
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);

    // Act
    const user = await userFromToken(signSession("marina", SECRET));

    // Assert
    expect(user).toMatchObject({ accountId: "marina", role: "manager" });
  });

  test("sem token, com token adulterado ou com o login desligado, nega", async () => {
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
    expect(await userFromToken(signSession("marina", SECRET))).toBeNull(); // login desligado
    vi.stubEnv("BASHO_DEMO_LOGIN_ENABLED", "true");
    expect(await userFromToken(undefined)).toBeNull();
    expect(await userFromToken("s1.eyJhIjoibWFyaW5hIn0.falsa")).toBeNull();
  });
});

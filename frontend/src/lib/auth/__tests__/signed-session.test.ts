import { afterEach, describe, expect, test, vi } from "vitest";

import { DemoSessionStore, SESSION_TTL_SECONDS, SignedSessionStore, sameOriginJson, sessionStore } from "../session";

const SECRET = "s".repeat(40);

afterEach(() => vi.unstubAllEnvs());

describe("sessão assinada (runtimes sem disco compartilhado)", () => {
  test("token criado é lido de volta com a conta e a função do cadastro", async () => {
    // Arrange
    const store = new SignedSessionStore(SECRET, () => 100000);

    // Act
    const token = await store.create("marina");

    // Assert
    expect(await store.read(token)).toMatchObject({ accountId: "marina", role: "manager" });
  });

  test("payload adulterado, outro segredo e lixo não concedem acesso", async () => {
    const store = new SignedSessionStore(SECRET, () => 100000);
    const token = await store.create("ana");
    const [prefix, payload, signature] = token.split(".");
    const forged = Buffer.from(JSON.stringify({
      version: 1, accountId: "marina", issuedAt: 100000, expiresAt: 100000 + SESSION_TTL_SECONDS * 1000,
    })).toString("base64url");

    expect(await store.read(`${prefix}.${forged}.${signature}`)).toBeNull();
    expect(await new SignedSessionStore("o".repeat(40), () => 100000).read(token)).toBeNull();
    expect(await store.read(`${prefix}.${payload}.zz`)).toBeNull();
    expect(await store.read("a".repeat(64))).toBeNull();
    expect(await store.read("v1." + "a".repeat(5000))).toBeNull();
    expect(await store.read(undefined)).toBeNull();
  });

  test("expira após o TTL", async () => {
    let now = 100000;
    const store = new SignedSessionStore(SECRET, () => now);
    const token = await store.create("rafael");

    now += SESSION_TTL_SECONDS * 1000;

    expect(await store.read(token)).toBeNull();
  });

  test("recusa conta inexistente e segredo curto", async () => {
    await expect(new SignedSessionStore(SECRET).create("intruso")).rejects.toThrow();
    expect(() => new SignedSessionStore("curto")).toThrow();
  });
});

describe("sessionStore()", () => {
  test("usa a sessão assinada quando há segredo e o arquivo quando não há", () => {
    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", SECRET);
    expect(sessionStore()).toBeInstanceOf(SignedSessionStore);

    vi.stubEnv("BASHO_DEMO_SESSION_SECRET", "");
    expect(sessionStore()).toBeInstanceOf(DemoSessionStore);
  });
});

describe("origem atrás de proxy (Railway/Vercel)", () => {
  const behindProxy = (origin: string) => new Request("http://10.0.0.5:8080/api/auth/login", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin,
      host: "10.0.0.5:8080",
      "x-forwarded-host": "basho.example",
      "x-forwarded-proto": "https",
    },
  });

  test("aceita a origem pública informada pela borda", () => {
    expect(sameOriginJson(behindProxy("https://basho.example"))).toBe(true);
  });

  test("recusa outra origem e o endereço interno", () => {
    expect(sameOriginJson(behindProxy("https://evil.test"))).toBe(false);
    expect(sameOriginJson(behindProxy("http://10.0.0.5:8080"))).toBe(false);
  });
});

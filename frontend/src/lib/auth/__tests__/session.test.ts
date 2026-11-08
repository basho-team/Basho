import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { scryptSync } from "node:crypto";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { DemoSessionStore, sameOriginJson, sessionToken, verifyDemoPassword, SESSION_TTL_SECONDS } from "../session";
import { authenticateDemo, consumeLoginAttempt } from "../login";
import { mayVisit } from "../shared";

let directory: string;
let now: number;
let store: DemoSessionStore;
beforeEach(async () => {
  directory = await mkdtemp(join(tmpdir(), "basho-demo-auth-"));
  now = 100000;
  store = new DemoSessionStore(directory, () => now);
  const salt = "a".repeat(32);
  vi.stubEnv("BASHO_DEMO_PASSWORD_HASH", "scrypt:" + salt + ":" + scryptSync("synthetic-password", salt, 64).toString("hex"));
});
afterEach(async () => { vi.unstubAllEnvs(); await rm(directory, { recursive: true, force: true }); });

describe("sessões locais revogáveis", () => {
  test("o token é opaco, a conta define a função e logout invalida a cópia do token", async () => {
    const token = await store.create("ana");
    expect(token).toMatch(/^[a-f0-9]{64}$/);
    expect(await store.read(token)).toMatchObject({ accountId: "ana", role: "researcher", personId: "p-ana" });
    await store.destroy(token);
    expect(await store.read(token)).toBeNull();
  });
  test("expiração, token adulterado e comprimento excessivo não concedem acesso", async () => {
    const token = await store.create("marina");
    expect(await store.read(token.slice(0, 63) + (token.endsWith("a") ? "b" : "a"))).toBeNull();
    expect(await store.read("../" + token)).toBeNull();
    expect(await store.read("a".repeat(100000))).toBeNull();
    now += SESSION_TTL_SECONDS * 1000;
    expect(await store.read(token)).toBeNull();
  });
  test("header de papel não cria sessão e cookie tem nome exato", () => {
    expect(sessionToken(new Request("http://localhost/", { headers: { "X-Demo-Role": "manager" } }))).toBeUndefined();
    expect(sessionToken(new Request("http://localhost/", { headers: { Cookie: "other=1; basho_demo_session=abc" } }))).toBe("abc");
  });
});

test("senha e papel precisam corresponder ao cadastro da conta", async () => {
  expect(await verifyDemoPassword("wrong")).toBe(false);
  expect(await authenticateDemo({ email: "ana@lumen.example", password: "synthetic-password", role: "manager" })).toBeNull();
  expect(await authenticateDemo({ email: "unknown@lumen.example", password: "synthetic-password", role: "researcher" })).toBeNull();
  expect(await authenticateDemo({ email: "ana@lumen.example", password: "synthetic-password", role: "researcher" })).toBe("ana");
});

test("CSRF recusa outra origem, troca de protocolo e ausência de origem", () => {
  const request = (origin?: string) => new Request("http://localhost:3002/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json", ...(origin ? { Origin: origin } : {}) }, body: "{}",
  });
  expect(sameOriginJson(request("http://localhost:3002"))).toBe(true);
  expect(sameOriginJson(request("https://localhost:3002"))).toBe(false);
  expect(sameOriginJson(request("http://evil.test"))).toBe(false);
  expect(sameOriginJson(request())).toBe(false);
});

test("tentativas de login têm limite e voltam a ser aceitas após a janela", () => {
  const email = "limit-test@lumen.example";
  for (let count = 0; count < 10; count++) expect(consumeLoginAttempt(email, 1)).toBe(true);
  expect(consumeLoginAttempt(email, 1)).toBe(false);
  expect(consumeLoginAttempt(email, 15 * 60 * 1000 + 2)).toBe(true);
});

test("cada função é limitada às próprias rotas, inclusive links profundos", () => {
  expect(mayVisit("researcher", "/pesquisador/relatorios/rep-ana")).toBe(true);
  expect(mayVisit("researcher", "/gerente/dossie")).toBe(false);
  expect(mayVisit("fiscal", "/gerente")).toBe(false);
  expect(mayVisit("manager", "/fiscal")).toBe(false);
  expect(mayVisit("fiscal", "/integracoes")).toBe(true);
});

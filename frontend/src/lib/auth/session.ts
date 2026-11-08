import "server-only";
import { createHash, createHmac, randomBytes, scrypt, timingSafeEqual } from "node:crypto";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";
import { z } from "zod";
import { accountUser, DEMO_ACCOUNTS, type DemoUser } from "./shared";

export const SESSION_COOKIE = "basho_demo_session";
export const SESSION_TTL_SECONDS = 4 * 60 * 60;
const TOKEN_PATTERN = /^[a-f0-9]{64}$/;
const deriveKey = promisify(scrypt);
const RecordSchema = z.object({
  version: z.literal(1),
  accountId: z.string(),
  issuedAt: z.number().int().nonnegative(),
  expiresAt: z.number().int().nonnegative(),
}).strict();

function isMissing(error: unknown): boolean {
  return error instanceof Error && "code" in error && error.code === "ENOENT";
}

/**
 * Entrada rápida da demonstração (opt-in): um clique na conta cria a sessão sem senha. Qualquer
 * pessoa que alcance o site entra com qualquer função; use só com dados sintéticos e nunca em
 * ambiente com dado real. Desligada por padrão.
 */
export function openAccessEnabled(): boolean {
  return process.env.BASHO_DEMO_OPEN_ACCESS === "true";
}

export function demoLoginEnabled(): boolean {
  return process.env.BASHO_DEMO_LOGIN_ENABLED === "true" || openAccessEnabled();
}

export function hasDemoPassword(): boolean {
  return /^scrypt:[a-f0-9]{32}:[a-f0-9]{128}$/.test(process.env.BASHO_DEMO_PASSWORD_HASH ?? "");
}

export async function verifyDemoPassword(password: string): Promise<boolean> {
  if (!hasDemoPassword() || password.length > 256) return false;
  const [, salt, encoded] = process.env.BASHO_DEMO_PASSWORD_HASH!.split(":");
  const actual = await deriveKey(password, salt, 64) as Buffer;
  return timingSafeEqual(actual, Buffer.from(encoded, "hex"));
}

/** Usuário da conta, com o UUID do backend quando `BASHO_DEMO_BACKEND_USERS` o mapeia. */
function userForAccount(account: (typeof DEMO_ACCOUNTS)[number]): DemoUser {
  const user = accountUser(account);
  const rawMapping = process.env.BASHO_DEMO_BACKEND_USERS;
  if (!rawMapping) return user;
  let mapping: unknown;
  try { mapping = JSON.parse(rawMapping); } catch { return user; }
  const parsedMapping = z.record(z.string(), z.uuid()).safeParse(mapping);
  return parsedMapping.success ? { ...user, backendUserId: parsedMapping.data[account.id] } : user;
}

/**
 * Sessão assinada (sem estado): HMAC-SHA256 sobre `{conta, emissão, expiração}` com
 * `BASHO_DEMO_SESSION_SECRET` (mín. 32 caracteres). Existe para ambiente serverless, onde não há
 * disco compartilhado. Troca revogação no servidor por independência de armazenamento: o logout
 * só apaga o cookie e o token vale até expirar (4 h). Sem o segredo, vale o arquivo local.
 */
const SIGNED_PREFIX = "s1.";
const MIN_SECRET_LENGTH = 32;

export function sessionSecret(): string | null {
  const value = process.env.BASHO_DEMO_SESSION_SECRET;
  return value && value.length >= MIN_SECRET_LENGTH ? value : null;
}

function signature(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

export function signSession(accountId: string, secret: string, now = Date.now()): string {
  if (!DEMO_ACCOUNTS.some(account => account.id === accountId)) throw new Error("Conta inválida");
  const payload = Buffer.from(JSON.stringify({
    a: accountId, i: now, e: now + SESSION_TTL_SECONDS * 1000,
  })).toString("base64url");
  return SIGNED_PREFIX + payload + "." + signature(secret, payload);
}

export function readSignedSession(token: string | undefined, secret: string | null, now = Date.now()): DemoUser | null {
  if (!token || !secret || token.length > 512 || !token.startsWith(SIGNED_PREFIX)) return null;
  const [payload, mac, extra] = token.slice(SIGNED_PREFIX.length).split(".");
  if (!payload || !mac || extra !== undefined) return null;
  const expected = Buffer.from(signature(secret, payload));
  const actual = Buffer.from(mac);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;
  let decoded: unknown;
  try { decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")); } catch { return null; }
  const parsed = z.object({ a: z.string(), i: z.number().int(), e: z.number().int() }).strict().safeParse(decoded);
  if (!parsed.success) return null;
  const { a, i, e } = parsed.data;
  if (i > now || e <= now || e - i !== SESSION_TTL_SECONDS * 1000) return null;
  const account = DEMO_ACCOUNTS.find(candidate => candidate.id === a);
  return account ? userForAccount(account) : null;
}

/** Cria a sessão: assinada se há segredo, senão arquivo local. */
export async function createSession(accountId: string): Promise<string> {
  const secret = sessionSecret();
  return secret ? signSession(accountId, secret) : sessionStore().create(accountId);
}

/** Arquivos locais da demonstração permitem revogação entre os runtimes do Next. */
export class DemoSessionStore {
  constructor(
    private readonly directory: string,
    private readonly now: () => number = Date.now,
  ) {}

  private path(token: string): string {
    return join(this.directory, createHash("sha256").update(token).digest("hex") + ".json");
  }

  async create(accountId: string): Promise<string> {
    if (!DEMO_ACCOUNTS.some(account => account.id === accountId)) throw new Error("Conta inválida");
    const token = randomBytes(32).toString("hex");
    const issuedAt = this.now();
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    await writeFile(this.path(token), JSON.stringify({
      version: 1, accountId, issuedAt, expiresAt: issuedAt + SESSION_TTL_SECONDS * 1000,
    }), { flag: "wx", mode: 0o600 });
    return token;
  }

  async read(token: string | undefined): Promise<DemoUser | null> {
    if (!token || !TOKEN_PATTERN.test(token)) return null;
    let raw: string;
    try {
      raw = await readFile(this.path(token), "utf8");
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
    let decoded: unknown;
    try { decoded = JSON.parse(raw); } catch { return null; }
    const parsed = RecordSchema.safeParse(decoded);
    if (!parsed.success) return null;
    const record = parsed.data;
    if (record.issuedAt > this.now() || record.expiresAt <= this.now()
      || record.expiresAt - record.issuedAt !== SESSION_TTL_SECONDS * 1000) return null;
    const account = DEMO_ACCOUNTS.find(candidate => candidate.id === record.accountId);
    if (!account) return null;
    return userForAccount(account);
  }

  async destroy(token: string | undefined): Promise<void> {
    if (!token || !TOKEN_PATTERN.test(token)) return;
    try { await unlink(this.path(token)); } catch (error) { if (!isMissing(error)) throw error; }
  }
}

export function sessionStore(): DemoSessionStore {
  return new DemoSessionStore(join(process.cwd(), ".local-demo", "sessions"));
}

export function sessionToken(request: Request): string | undefined {
  const cookie = request.headers.get("cookie") ?? "";
  const entry = cookie.split(";").map(item => item.trim()).find(item => item.startsWith(SESSION_COOKIE + "="));
  return entry?.slice(SESSION_COOKIE.length + 1);
}

/**
 * Único caminho de leitura da sessão: proxy, rotas e layout passam por aqui. Ler o arquivo direto
 * (como o layout fazia) ignorava a sessão assinada e deixava o app em laço de redirecionamento.
 */
export async function userFromToken(token: string | undefined): Promise<DemoUser | null> {
  if (!demoLoginEnabled()) return null;
  if (token?.startsWith(SIGNED_PREFIX)) return readSignedSession(token, sessionSecret());
  return sessionStore().read(token);
}

export async function userFromRequest(request: Request): Promise<DemoUser | null> {
  return userFromToken(sessionToken(request));
}

export function sameOriginJson(request: Request): boolean {
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get("content-type") ?? "")) return false;
  const site = request.headers.get("sec-fetch-site");
  if (site !== null && site !== "same-origin") return false;
  const origin = request.headers.get("origin");
  return origin !== null && origin === publicOrigin(request);
}

function firstForwarded(value: string | null): string | undefined {
  const first = value?.split(",")[0]?.trim();
  return first ? first : undefined;
}

/**
 * Origem pública vista pelo navegador. Atrás do proxy do Railway, `request.url` é o
 * endereço interno do container; host e protocolo públicos vêm de `X-Forwarded-*`
 * (definidos pela borda). O navegador não deixa um site terceiro forjar `Origin`.
 */
export function publicOrigin(request: Request): string {
  const url = new URL(request.url);
  const proto = firstForwarded(request.headers.get("x-forwarded-proto")) ?? url.protocol.replace(/:$/, "");
  const host = firstForwarded(request.headers.get("x-forwarded-host")) ?? request.headers.get("host") ?? url.host;
  return `${proto}://${host}`;
}

export function authError(status: number, message: string): Response {
  return Response.json({ message }, { status, headers: { "Cache-Control": "no-store" } });
}

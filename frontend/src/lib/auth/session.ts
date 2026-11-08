import "server-only";
import { createHash, randomBytes, scrypt, timingSafeEqual } from "node:crypto";
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

export function demoLoginEnabled(): boolean {
  return process.env.BASHO_DEMO_LOGIN_ENABLED === "true";
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
    const user = accountUser(account);
    const rawMapping = process.env.BASHO_DEMO_BACKEND_USERS;
    if (!rawMapping) return user;
    let mapping: unknown;
    try { mapping = JSON.parse(rawMapping); } catch { return user; }
    const parsedMapping = z.record(z.string(), z.uuid()).safeParse(mapping);
    return parsedMapping.success ? { ...user, backendUserId: parsedMapping.data[account.id] } : user;
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

export async function userFromRequest(request: Request): Promise<DemoUser | null> {
  if (!demoLoginEnabled()) return null;
  return sessionStore().read(sessionToken(request));
}

export function sameOriginJson(request: Request): boolean {
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get("content-type") ?? "")) return false;
  const site = request.headers.get("sec-fetch-site");
  if (site !== null && site !== "same-origin") return false;
  const origin = request.headers.get("origin");
  return origin !== null && origin === new URL(request.url).origin;
}

export function authError(status: number, message: string): Response {
  return Response.json({ message }, { status, headers: { "Cache-Control": "no-store" } });
}

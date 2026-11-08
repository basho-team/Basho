import "server-only";
import { createHash } from "node:crypto";
import { z } from "zod";
import { DEMO_ACCOUNTS, RoleSchema } from "./shared";
import { verifyDemoPassword } from "./session";

export const LoginSchema = z.object({
  email: z.email().max(254).transform(value => value.toLowerCase()),
  password: z.string().min(1).max(256),
  role: RoleSchema,
}).strict();
const ATTEMPT_WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 10;
const MAX_TRACKED_KEYS = 1000;
const attempts = new Map<string, { count: number; expires: number }>();

export function consumeLoginAttempt(email: string, now = Date.now()): boolean {
  for (const [key, value] of attempts) if (value.expires <= now) attempts.delete(key);
  const key = createHash("sha256").update(email).digest("hex");
  const found = attempts.get(key);
  if (found && found.count >= MAX_ATTEMPTS) return false;
  if (!found && attempts.size >= MAX_TRACKED_KEYS) return false;
  attempts.set(key, { count: (found?.count ?? 0) + 1, expires: found?.expires ?? now + ATTEMPT_WINDOW_MS });
  return true;
}

export async function authenticateDemo(input: z.infer<typeof LoginSchema>): Promise<string | null> {
  const account = DEMO_ACCOUNTS.find(candidate => candidate.email === input.email);
  const passwordMatches = await verifyDemoPassword(input.password);
  if (!account || !passwordMatches || account.role !== input.role) return null;
  return account.id;
}

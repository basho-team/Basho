import "server-only";
import { z } from "zod";
import { ReviewerRoleSchema, type ReviewerRole } from "@/lib/bff/contract";

/** Mesmo mínimo do backend (`MIN_IDENTITY_SECRET_LENGTH`). */
export const MIN_IDENTITY_SECRET_LENGTH = 32;
const DEFAULT_BACKEND_URL = "http://localhost:8000";

export interface DemoReviewer {
  userId: string;
  role: ReviewerRole;
}

export interface ServerEnv {
  backendUrl: string;
  /** `null` = não configurado: a revisão fica indisponível (503), como no backend. */
  reviewerIdentitySecret: string | null;
  /** Revisores que a troca de papel da demonstração pode assumir. */
  demoReviewers: readonly DemoReviewer[];
}

/** Configuração inválida derruba a requisição com mensagem sem valores (ADR-0006). */
export class ServerConfigError extends Error {
  constructor(variable: string) {
    super(`variável de ambiente inválida: ${variable}`);
    this.name = "ServerConfigError";
  }
}

const UuidSchema = z.uuid();

/** `BASHO_DEMO_REVIEWERS="<uuid>:researcher,<uuid>:manager"`. */
function parseDemoReviewers(raw: string | undefined): DemoReviewer[] {
  if (!raw?.trim()) return [];
  return raw.split(",").map((entry) => {
    const [userId, role, ...rest] = entry.trim().split(":");
    const parsedRole = ReviewerRoleSchema.safeParse(role);
    if (rest.length > 0 || !UuidSchema.safeParse(userId).success || !parsedRole.success) {
      throw new ServerConfigError("BASHO_DEMO_REVIEWERS");
    }
    return { userId: userId.toLowerCase(), role: parsedRole.data };
  });
}

function parseSecret(raw: string | undefined): string | null {
  if (!raw) return null;
  if (raw.length < MIN_IDENTITY_SECRET_LENGTH) throw new ServerConfigError("REVIEWER_IDENTITY_SECRET");
  return raw;
}

function parseBackendUrl(raw: string | undefined): string {
  const parsed = z.url({ protocol: /^https?$/ }).safeParse(raw ?? DEFAULT_BACKEND_URL);
  if (!parsed.success) throw new ServerConfigError("BASHO_API_URL");
  return parsed.data.replace(/\/+$/, "");
}

/**
 * Lê a configuração do servidor a cada chamada (variáveis sem `NEXT_PUBLIC_`, nunca vão
 * para o bundle do cliente). `source` existe para os testes.
 */
export function readServerEnv(source: Readonly<Record<string, string | undefined>> = process.env): ServerEnv {
  return {
    backendUrl: parseBackendUrl(source.BASHO_API_URL),
    reviewerIdentitySecret: parseSecret(source.REVIEWER_IDENTITY_SECRET),
    demoReviewers: parseDemoReviewers(source.BASHO_DEMO_REVIEWERS),
  };
}

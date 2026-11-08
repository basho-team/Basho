import "server-only";
import type { z } from "zod";
import { BffErrorCode } from "@/lib/bff/contract";
import { userFromRequest, sameOriginJson } from "@/lib/auth/session";
import { boundedJson } from "@/lib/auth/http";
import type { DemoUser } from "@/lib/auth/shared";
import type { ApiError } from "@/lib/contracts/provisional";
import { readServerEnv, ServerConfigError, type DemoReviewer, type ServerEnv } from "@/lib/server/env";

/**
 * Núcleo do BFF: identidade da demo, proteção de borda e repasse ao backend.
 *
 * Local demo login binds identity to the verified session. Browser headers and body
 * cannot grant a role. Backend identity remains provisional until production auth (#47).
 */

/** Headers de identidade humana do backend (#39, #5 — `basho.identity`). */
export const USER_ID_HEADER = "X-Basho-User-Id";
export const ROLE_HEADER = "X-Basho-Role";
export const IDENTITY_SECRET_HEADER = "X-Basho-Identity-Secret";

const BACKEND_TIMEOUT_MS = 10_000;
const MAX_BODY_BYTES = 64 * 1024;
const NO_STORE = { "Cache-Control": "no-store" } as const;

export interface BffDeps {
  env: () => ServerEnv;
  fetch: typeof fetch;
  correlationId: () => string;
  session?: (request: Request) => Promise<DemoUser | null>;
}

export const defaultDeps: BffDeps = {
  env: () => readServerEnv(),
  fetch: (input, init) => fetch(input, init),
  session: userFromRequest,
  correlationId: () => `bff-${crypto.randomUUID()}`,
};

/** Mensagens fixas comuns: nada do backend ou da configuração vaza para o navegador. */
export const COMMON_MESSAGES = {
  invalidRequest: "Requisição inválida.",
  crossSite: "Requisição de outra origem recusada.",
  noRole: "Escolha um papel da demonstração (pesquisador ou gerente) para continuar.",
  invalidResponse: "Resposta inesperada do servidor do Basho.",
  tooLarge: "O histórico deste projeto passou do limite de leitura.",
  backend: "Não foi possível falar com o servidor do Basho. Tente de novo.",
  config: "Configuração do servidor inválida. Avise a equipe técnica.",
} as const;

/** Mensagens específicas de cada rota. */
export interface RouteMessages {
  notFound: string;
  forbidden: string;
  unavailable: string;
  invalid: string;
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
  correlationId: string,
  options: { retryable?: boolean; extra?: Record<string, unknown> } = {},
): Response {
  const body: ApiError & Record<string, unknown> = {
    ...options.extra,
    code,
    message,
    correlation_id: correlationId,
    retryable: options.retryable ?? false,
  };
  return Response.json(body, { status, headers: NO_STORE });
}

/**
 * Proteção contra CSRF nas ações humanas:
 * - exige `Content-Type: application/json`, o que força preflight em requisição cross-site
 *   e barra `<form enctype="text/plain">`;
 * - exige Origin com protocolo, host e porta exatos; recusa Sec-Fetch-Site diferente de same-origin.
 * Ausência de Origin é recusada. A sessão é validada separadamente.
 */
export function isSameOriginJson(request: Request): boolean {
  return sameOriginJson(request);
}

/** Limite em bytes checado antes e durante a leitura do stream. */
export async function readJsonBody(request: Request): Promise<unknown> {
  const body = await boundedJson(request, MAX_BODY_BYTES);
  return body instanceof Response ? undefined : body;
}

export interface Gate {
  env: ServerEnv;
  cid: string;
}

/**
 * Abre a requisição: configuração válida, segredo e lista de revisores presentes.
 * Sem segredo, o backend recusaria (503), então nem chamamos.
 */
export function openGate(deps: BffDeps, cid: string, unavailableCode: string, unavailable: string): Gate | Response {
  let env: ServerEnv;
  try {
    env = deps.env();
  } catch (error) {
    if (error instanceof ServerConfigError) return errorResponse(500, BffErrorCode.serverConfig, COMMON_MESSAGES.config, cid);
    throw error;
  }
  if (!env.reviewerIdentitySecret || env.demoReviewers.length === 0) {
    return errorResponse(503, unavailableCode, unavailable, cid);
  }
  return { env, cid };
}

/** Identidade da sessão validada e vinculada explicitamente ao usuário do backend. */
export async function identityFromRole(request: Request, env: ServerEnv, deps: BffDeps): Promise<DemoReviewer | null> {
  const user = await (deps.session ?? userFromRequest)(request);
  if (!user || user.role === "fiscal" || !user.backendUserId) return null;
  return env.demoReviewers.find(reviewer => reviewer.userId === user.backendUserId && reviewer.role === user.role) ?? null;
}

/** O corpo nunca concede identidade: precisa corresponder à sessão validada. */
export async function identityFromPair(request: Request, env: ServerEnv, userId: string, role: string, deps: BffDeps): Promise<DemoReviewer | null> {
  const identity = await identityFromRole(request, env, deps);
  return identity?.userId === userId.toLowerCase() && identity.role === role ? identity : null;
}

export interface ForwardSpec {
  method: "GET" | "POST" | "DELETE";
  /** Caminho já validado (IDs como UUID, query só de valores conhecidos). */
  path: string;
  identity: DemoReviewer;
  body?: unknown;
  /** Um ou mais status de sucesso (ex.: 202 criado e 200 já existente). */
  okStatus: number | readonly number[];
  okSchema: z.ZodType;
  /** Headers extras para o backend (ex.: `Idempotency-Key`). Nunca vêm do navegador. */
  headers?: Record<string, string>;
  unavailableCode: string;
  invalidCode: string;
  messages: RouteMessages;
  onConflict?: (body: unknown, cid: string) => Response;
  /** Erros da rota com mensagem própria e segura (ex.: como compartilhar a pasta). `null` = padrão. */
  onError?: (status: number, body: unknown, cid: string) => Response | null;
}

function identityHeaders(gate: Gate, identity: DemoReviewer): Record<string, string> {
  return {
    [USER_ID_HEADER]: identity.userId,
    [ROLE_HEADER]: identity.role,
    [IDENTITY_SECRET_HEADER]: gate.env.reviewerIdentitySecret ?? "",
  };
}

/**
 * Repassa ao backend com a identidade injetada e devolve só o que o contrato conhece
 * (`z.object` descarta campos extras). Erros viram mensagens fixas.
 */
export async function forward(deps: BffDeps, gate: Gate, spec: ForwardSpec): Promise<Response> {
  const { cid } = gate;
  let res: Response;
  try {
    res = await deps.fetch(`${gate.env.backendUrl}/api/v1${spec.path}`, {
      method: spec.method,
      cache: "no-store",
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
      headers: {
        Accept: "application/json",
        "X-Request-Id": cid,
        ...(spec.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...identityHeaders(gate, spec.identity),
        ...spec.headers,
      },
      body: spec.body === undefined ? undefined : JSON.stringify(spec.body),
    });
  } catch {
    return errorResponse(502, BffErrorCode.backendUnavailable, COMMON_MESSAGES.backend, cid, { retryable: true });
  }

  const body: unknown = await res.json().catch(() => null);
  const accepted = typeof spec.okStatus === "number" ? [spec.okStatus] : spec.okStatus;
  if (accepted.includes(res.status)) {
    const parsed = spec.okSchema.safeParse(body);
    if (!parsed.success) {
      return errorResponse(502, BffErrorCode.invalidResponse, COMMON_MESSAGES.invalidResponse, cid, { retryable: true });
    }
    return Response.json(parsed.data, { status: res.status, headers: NO_STORE });
  }
  return mapError(res.status, body, cid, spec);
}

function mapError(status: number, body: unknown, cid: string, spec: ForwardSpec): Response {
  const { messages } = spec;
  const custom = spec.onError?.(status, body, cid) ?? null;
  if (custom) return custom;
  if (status === 409 && spec.onConflict) return spec.onConflict(body, cid);
  // 401 = segredo divergente entre BFF e backend: é falha de configuração, não do usuário.
  if (status === 503 || status === 401) return errorResponse(503, spec.unavailableCode, messages.unavailable, cid);
  if (status === 403) return errorResponse(403, BffErrorCode.forbidden, messages.forbidden, cid);
  if (status === 404) return errorResponse(404, BffErrorCode.notFound, messages.notFound, cid);
  if (status === 422) return errorResponse(422, spec.invalidCode, messages.invalid, cid);
  if (status === 413) return errorResponse(502, BffErrorCode.tooLarge, COMMON_MESSAGES.tooLarge, cid);
  return errorResponse(502, BffErrorCode.backendUnavailable, COMMON_MESSAGES.backend, cid, { retryable: true });
}

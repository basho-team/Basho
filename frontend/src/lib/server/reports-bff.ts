import "server-only";
import { z } from "zod";
import { ApiReportVersionOutSchema, ApiReviewOutSchema } from "@/lib/api/reports";
import { BffErrorCode, BffReviewRequestSchema } from "@/lib/bff/contract";
import type { ApiError } from "@/lib/contracts/provisional";
import { readServerEnv, ServerConfigError, type ServerEnv } from "@/lib/server/env";

/** Headers do placeholder de identidade do backend (#39/#47). */
export const USER_ID_HEADER = "X-Basho-User-Id";
export const ROLE_HEADER = "X-Basho-Role";
export const IDENTITY_SECRET_HEADER = "X-Basho-Identity-Secret";

const BACKEND_TIMEOUT_MS = 10_000;
const MAX_BODY_BYTES = 64 * 1024;
const JSON_CONTENT_TYPE = /^application\/json\s*(;|$)/i;
const VersionIdSchema = z.uuid();
const BackendConflictSchema = z.object({ current_version_id: z.uuid() });

export interface BffDeps {
  env: () => ServerEnv;
  fetch: typeof fetch;
  correlationId: () => string;
}

export const defaultDeps: BffDeps = {
  env: () => readServerEnv(),
  fetch: (input, init) => fetch(input, init),
  correlationId: () => `bff-${crypto.randomUUID()}`,
};

/** Mensagens fixas: nada do backend ou da configuração vaza para o navegador. */
const MESSAGES = {
  invalidRequest: "Requisição inválida.",
  crossSite: "Requisição de outra origem recusada.",
  invalidResponse: "Resposta inesperada do servidor do Basho.",
  notFound: "Relatório não encontrado.",
  forbidden: "Este papel não pode revisar este relatório.",
  conflict: "Esta versão não é mais a atual. Recarregue para ver a versão nova.",
  unavailable: "Revisão indisponível no momento. Avise a equipe técnica.",
  invalidReview: "A revisão ou correção não foi aceita para esta versão. Confira os campos.",
  backend: "Não foi possível falar com o servidor do Basho. Tente de novo.",
  config: "Configuração do servidor inválida. Avise a equipe técnica.",
} as const;

function errorResponse(
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
  return Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

function passthrough(data: unknown, status: number): Response {
  return Response.json(data, { status, headers: { "Cache-Control": "no-store" } });
}

async function callBackend(deps: BffDeps, url: string, init: RequestInit): Promise<Response | null> {
  try {
    return await deps.fetch(url, { ...init, cache: "no-store", signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS) });
  } catch {
    return null;
  }
}

function loadEnv(deps: BffDeps): ServerEnv | null {
  try {
    return deps.env();
  } catch (error) {
    if (error instanceof ServerConfigError) return null;
    throw error;
  }
}

/** GET de uma versão de relatório. Leitura não exige identidade no backend atual. */
export async function getReportVersion(rawVersionId: string, deps: BffDeps = defaultDeps): Promise<Response> {
  const cid = deps.correlationId();
  const versionId = VersionIdSchema.safeParse(rawVersionId);
  if (!versionId.success) return errorResponse(400, BffErrorCode.invalidRequest, MESSAGES.invalidRequest, cid);
  const env = loadEnv(deps);
  if (!env) return errorResponse(500, BffErrorCode.serverConfig, MESSAGES.config, cid);

  const res = await callBackend(deps, `${env.backendUrl}/api/v1/reports/${versionId.data}`, {
    method: "GET",
    headers: { Accept: "application/json", "X-Request-Id": cid },
  });
  if (!res) return errorResponse(502, BffErrorCode.backendUnavailable, MESSAGES.backend, cid, { retryable: true });
  if (res.status === 200) return validated(ApiReportVersionOutSchema, res, 200, cid);
  if (res.status === 404) return errorResponse(404, BffErrorCode.notFound, MESSAGES.notFound, cid);
  return errorResponse(502, BffErrorCode.backendUnavailable, MESSAGES.backend, cid, { retryable: true });
}

/**
 * Repassa só o que o contrato conhece: `z.object` descarta campos extras, então um campo
 * interno que o backend venha a devolver não chega ao navegador.
 */
async function validated(schema: z.ZodType, res: Response, status: number, cid: string): Promise<Response> {
  const parsed = schema.safeParse(await res.json().catch(() => null));
  if (!parsed.success) {
    return errorResponse(502, BffErrorCode.invalidResponse, MESSAGES.invalidResponse, cid, { retryable: true });
  }
  return passthrough(parsed.data, status);
}

/**
 * Proteção contra CSRF na ação formal:
 * - exige `Content-Type: application/json`, o que força preflight em requisição cross-site
 *   e barra `<form enctype="text/plain">`;
 * - recusa `Origin` de outro host e `Sec-Fetch-Site` diferente de `same-origin`.
 * Clientes sem esses headers (ex.: curl na rede da demo) passam: isto não é autenticação.
 */
export function isSameOriginJson(request: Request): boolean {
  if (!JSON_CONTENT_TYPE.test(request.headers.get("content-type") ?? "")) return false;
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite !== null && fetchSite !== "same-origin") return false;
  const origin = request.headers.get("origin");
  if (origin === null) return true;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? new URL(request.url).host;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Limite em bytes, checado pelo `Content-Length` antes de ler e de novo depois. */
async function readJsonBody(request: Request): Promise<unknown> {
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(declared) || declared > MAX_BODY_BYTES) return undefined;
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

async function mapReviewResponse(res: Response, cid: string): Promise<Response> {
  if (res.status === 201) return validated(ApiReviewOutSchema, res, 201, cid);
  if (res.status === 409) {
    const conflict = BackendConflictSchema.safeParse(await res.json().catch(() => null));
    const extra = conflict.success ? { current_version_id: conflict.data.current_version_id } : undefined;
    return errorResponse(409, BffErrorCode.versionConflict, MESSAGES.conflict, cid, { extra });
  }
  // 401 = segredo divergente entre BFF e backend: é falha de configuração, não do usuário.
  if (res.status === 503 || res.status === 401) {
    return errorResponse(503, BffErrorCode.reviewUnavailable, MESSAGES.unavailable, cid);
  }
  if (res.status === 403) return errorResponse(403, BffErrorCode.forbidden, MESSAGES.forbidden, cid);
  if (res.status === 404) return errorResponse(404, BffErrorCode.notFound, MESSAGES.notFound, cid);
  if (res.status === 422) return errorResponse(422, BffErrorCode.invalidReview, MESSAGES.invalidReview, cid);
  return errorResponse(502, BffErrorCode.backendUnavailable, MESSAGES.backend, cid, { retryable: true });
}

/**
 * POST de revisão (ação formal, só humano — ADR-0005). O BFF:
 * 1. recusa requisição de outra origem (CSRF);
 * 2. valida o corpo e o ID da versão;
 * 3. aceita só revisores da lista do servidor, com o papel configurado para eles;
 * 4. injeta os headers de identidade e o segredo, que nunca saem do servidor.
 *
 * ATENÇÃO: o BFF NÃO autentica. Quem alcança o Next escolhe qual revisor da lista quer ser;
 * a lista só limita os pares possíveis. Placeholder até a auth real (#47); não publique o
 * deploy sem uma camada de acesso (basic auth, Vercel protection).
 */
export async function postReview(
  rawVersionId: string,
  request: Request,
  deps: BffDeps = defaultDeps,
): Promise<Response> {
  const cid = deps.correlationId();
  if (!isSameOriginJson(request)) return errorResponse(403, BffErrorCode.forbidden, MESSAGES.crossSite, cid);
  const versionId = VersionIdSchema.safeParse(rawVersionId);
  const body = BffReviewRequestSchema.safeParse(await readJsonBody(request));
  if (!versionId.success || !body.success) {
    return errorResponse(400, BffErrorCode.invalidRequest, MESSAGES.invalidRequest, cid);
  }

  const env = loadEnv(deps);
  if (!env?.reviewerIdentitySecret || env.demoReviewers.length === 0) {
    return errorResponse(503, BffErrorCode.reviewUnavailable, MESSAGES.unavailable, cid);
  }

  const { reviewer_id, role, ...review } = body.data;
  const reviewer = env.demoReviewers.find((r) => r.userId === reviewer_id.toLowerCase());
  if (!reviewer || reviewer.role !== role) {
    return errorResponse(403, BffErrorCode.forbidden, MESSAGES.forbidden, cid);
  }

  const res = await callBackend(deps, `${env.backendUrl}/api/v1/reports/${versionId.data}/review`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Request-Id": cid,
      [USER_ID_HEADER]: reviewer.userId,
      [ROLE_HEADER]: reviewer.role,
      [IDENTITY_SECRET_HEADER]: env.reviewerIdentitySecret,
    },
    body: JSON.stringify(review),
  });
  if (!res) return errorResponse(502, BffErrorCode.backendUnavailable, MESSAGES.backend, cid, { retryable: true });
  return mapReviewResponse(res, cid);
}

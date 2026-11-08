import "server-only";
import { z } from "zod";
import { BffErrorCode } from "@/lib/bff/contract";
import {
  BffLinkRequestSchema,
  IntegrationErrorCode,
  IntegrationsConfigSchema,
  AgentRunSchema,
  LinkSchema,
  LinksSchema,
  PublicationsSchema,
} from "@/lib/bff/integrations-contract";
import {
  COMMON_MESSAGES,
  defaultDeps,
  errorResponse,
  forward,
  identityFromRole,
  isSameOriginJson,
  openGate,
  readJsonBody,
  type BffDeps,
  type Gate,
  type RouteMessages,
} from "@/lib/server/bff-core";
import type { DemoReviewer } from "@/lib/server/env";

/** Rotas de links autorizados e publicação em Drive/Notion (ADR-0010). */

const UuidSchema = z.uuid();

const MESSAGES: RouteMessages = {
  notFound: "Projeto ou link não encontrado.",
  forbidden: "Só o gerente autoriza ou revoga links.",
  unavailable: "Integrações indisponíveis no momento. Avise a equipe técnica.",
  invalid: "O link não foi aceito. Confira o endereço.",
};

const ROUTE = {
  unavailableCode: BffErrorCode.identityUnavailable,
  invalidCode: IntegrationErrorCode.linkRejected,
  messages: MESSAGES,
} as const;

const BackendLinkErrorSchema = z.object({ code: z.string().min(1).max(60), detail: z.string().min(1).max(500) });

/**
 * Erros de link com orientação própria (como compartilhar a pasta). O texto vem fixo do
 * backend, que nunca repassa o corpo do provedor; mesmo assim limitamos o tamanho aqui.
 */
function linkError(status: number, body: unknown, cid: string): Response | null {
  const parsed = BackendLinkErrorSchema.safeParse(body);
  if (!parsed.success) return null;
  const { code, detail } = parsed.data;
  if (status === 422) return errorResponse(422, IntegrationErrorCode.linkRejected, detail, cid, { extra: { reason: code } });
  if (status === 503 && code === "not_configured") {
    return errorResponse(503, IntegrationErrorCode.notConfigured, detail, cid, { extra: { reason: code } });
  }
  if (status === 502) return errorResponse(502, IntegrationErrorCode.providerUnavailable, detail, cid, { retryable: true });
  return null;
}

interface Opened {
  gate: Gate;
  identity: DemoReviewer;
}

async function openSession(request: Request, deps: BffDeps): Promise<Opened | Response> {
  const cid = deps.correlationId();
  const gate = openGate(deps, cid, ROUTE.unavailableCode, MESSAGES.unavailable);
  if (gate instanceof Response) return gate;
  // Identidade só da sessão validada no servidor (ADR-0011): headers do navegador não valem.
  const identity = await identityFromRole(request, gate.env, deps);
  if (!identity) return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.noRole, cid);
  return { gate, identity };
}

function parseId(raw: string, deps: BffDeps): string | Response {
  const id = UuidSchema.safeParse(raw);
  return id.success ? id.data : errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, deps.correlationId());
}

function managerOnly(opened: Opened): Response | null {
  return opened.identity.role === "manager"
    ? null
    : errorResponse(403, BffErrorCode.forbidden, MESSAGES.forbidden, opened.gate.cid);
}

export async function getConfig(request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: "/integrations/config",
    identity: opened.identity,
    okStatus: 200,
    okSchema: IntegrationsConfigSchema,
  });
}

export async function listLinks(rawProjectId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const projectId = parseId(rawProjectId, deps);
  if (projectId instanceof Response) return projectId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: `/projects/${projectId}/links`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: LinksSchema,
  });
}

/** Autoriza um link: só gerente. O backend verifica o acesso antes de gravar. */
export async function postLink(rawProjectId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  if (!isSameOriginJson(request)) {
    return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.crossSite, deps.correlationId());
  }
  const body = BffLinkRequestSchema.safeParse(await readJsonBody(request));
  if (!body.success) return errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, deps.correlationId());
  const projectId = parseId(rawProjectId, deps);
  if (projectId instanceof Response) return projectId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  const denied = managerOnly(opened);
  if (denied) return denied;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "POST",
    path: `/projects/${projectId}/links`,
    identity: opened.identity,
    body: body.data,
    okStatus: 201,
    okSchema: LinkSchema,
    onError: linkError,
  });
}

export async function deleteLink(
  rawProjectId: string,
  rawLinkId: string,
  request: Request,
  deps: BffDeps = defaultDeps,
): Promise<Response> {
  if (request.headers.get("sec-fetch-site") !== null && request.headers.get("sec-fetch-site") !== "same-origin") {
    return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.crossSite, deps.correlationId());
  }
  const projectId = parseId(rawProjectId, deps);
  if (projectId instanceof Response) return projectId;
  const linkId = parseId(rawLinkId, deps);
  if (linkId instanceof Response) return linkId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  const denied = managerOnly(opened);
  if (denied) return denied;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "DELETE",
    path: `/projects/${projectId}/links/${linkId}`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: LinkSchema,
  });
}

export async function listPublications(
  rawProjectId: string,
  request: Request,
  deps: BffDeps = defaultDeps,
): Promise<Response> {
  const projectId = parseId(rawProjectId, deps);
  if (projectId instanceof Response) return projectId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: `/projects/${projectId}/publications`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: PublicationsSchema,
  });
}

const PERIOD_DAYS = 30;
const DAY_MS = 86_400_000;
const REPORT_TIMEZONE = "America/Sao_Paulo";

function isoDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * "Gerar relatório": pede ao agente o relatório dos últimos 30 dias. O pesquisador pede o próprio;
 * o gerente pede o do primeiro pesquisador da lista. O período e o pesquisador vêm do servidor,
 * nunca do navegador.
 */
export async function postGenerate(rawProjectId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  if (request.headers.get("sec-fetch-site") !== null && request.headers.get("sec-fetch-site") !== "same-origin") {
    return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.crossSite, deps.correlationId());
  }
  const projectId = parseId(rawProjectId, deps);
  if (projectId instanceof Response) return projectId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  const researcher =
    opened.identity.role === "researcher" ? opened.identity : opened.gate.env.demoReviewers.find((r) => r.role === "researcher");
  if (!researcher) return errorResponse(503, BffErrorCode.identityUnavailable, MESSAGES.unavailable, opened.gate.cid);
  const now = Date.now();
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "POST",
    path: `/projects/${projectId}/agent-runs`,
    identity: opened.identity,
    headers: { "Idempotency-Key": `ui-${projectId}-${now}` },
    body: {
      task_kind: "research_report",
      researcher_id: researcher.userId,
      period: {
        start: isoDate(now - (PERIOD_DAYS - 1) * DAY_MS),
        end: isoDate(now),
        timezone: REPORT_TIMEZONE,
        periodicity: "monthly",
      },
    },
    okStatus: [200, 202],
    okSchema: AgentRunSchema,
    onError: (status, _body, cid) =>
      status === 429
        ? errorResponse(429, IntegrationErrorCode.tooManyRuns, "Há relatórios demais em andamento. Aguarde a conclusão.", cid, {
            retryable: true,
          })
        : null,
  });
}

export async function getRun(rawRunId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const runId = parseId(rawRunId, deps);
  if (runId instanceof Response) return runId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: `/agent-runs/${runId}`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: AgentRunSchema,
  });
}

/** "Publicar agora": enfileira o que está verificado; o worker escreve nos destinos. */
export async function postPublish(rawProjectId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  if (request.headers.get("sec-fetch-site") !== null && request.headers.get("sec-fetch-site") !== "same-origin") {
    return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.crossSite, deps.correlationId());
  }
  const projectId = parseId(rawProjectId, deps);
  if (projectId instanceof Response) return projectId;
  const opened = await openSession(request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "POST",
    path: `/projects/${projectId}/publications`,
    identity: opened.identity,
    okStatus: 202,
    okSchema: PublicationsSchema,
  });
}

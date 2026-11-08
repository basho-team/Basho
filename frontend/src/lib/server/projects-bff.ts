import "server-only";
import { z } from "zod";
import {
  ArtifactStatusSchema,
  ConflictSchema,
  DossierSchema,
  PendingAnswerOutSchema,
  PendingPageSchema,
  ProjectSchema,
  ApprovalSchema,
} from "@/lib/api/projects";
import {
  BffAnswerRequestSchema,
  BffApprovalRequestSchema,
  BffErrorCode,
  PendingQuerySchema,
} from "@/lib/bff/contract";
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

/** Rotas de projetos, pendências, aprovação formal e dossiê (#5, PR #54). */

const UuidSchema = z.uuid();

const MESSAGES: RouteMessages = {
  notFound: "Projeto, pendência ou artefato não encontrado.",
  forbidden: "Este papel não pode fazer esta ação.",
  unavailable: "Ação indisponível no momento. Avise a equipe técnica.",
  invalid: "A resposta não foi aceita para esta pendência. Confira o texto.",
};

/** Motivos de 409 conhecidos (`ConflictOut.code`), com mensagens fixas em português. */
const CONFLICT_MESSAGES: Record<string, string> = {
  pending_closed: "Esta pendência já foi respondida ou encerrada. Recarregamos a lista.",
  approval_via_artifact_endpoint: "Esta pendência se resolve aprovando ou rejeitando o artefato.",
  already_decided: "Este artefato já tem decisão formal.",
  artifact_not_verified: "Só artefato verificado pode ser aprovado.",
  artifact_not_rejectable: "Este artefato não pode ser rejeitado no estado atual.",
  open_pending: "O artefato ainda tem pendência aberta.",
};
const DEFAULT_CONFLICT = "Ação inválida no estado atual. Recarregue a tela.";

const ROUTE = {
  unavailableCode: BffErrorCode.identityUnavailable,
  invalidCode: BffErrorCode.invalidAnswer,
  messages: MESSAGES,
} as const;

/** 409 de pendência/aprovação: repassa só o motivo conhecido e o estado atual válido. */
function stateConflict(body: unknown, cid: string): Response {
  const conflict = ConflictSchema.safeParse(body);
  const reason = conflict.success && conflict.data.code in CONFLICT_MESSAGES ? conflict.data.code : null;
  const status = ArtifactStatusSchema.safeParse(conflict.success ? conflict.data.current_status : null);
  return errorResponse(409, BffErrorCode.stateConflict, reason ? CONFLICT_MESSAGES[reason] : DEFAULT_CONFLICT, cid, {
    extra: { reason, current_status: status.success ? status.data : null },
  });
}

interface Opened {
  gate: Gate;
  identity: DemoReviewer;
  id: string;
}

/** Valida o ID, a configuração e o papel declarado. Devolve a resposta de erro se falhar. */
function open(rawId: string, request: Request, deps: BffDeps): Opened | Response {
  const cid = deps.correlationId();
  const id = UuidSchema.safeParse(rawId);
  if (!id.success) return errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, cid);
  const gate = openGate(deps, cid, ROUTE.unavailableCode, MESSAGES.unavailable);
  if (gate instanceof Response) return gate;
  const identity = identityFromRole(request, gate.env);
  if (!identity) return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.noRole, cid);
  return { gate, identity, id: id.data };
}

async function openPost(rawId: string, request: Request, deps: BffDeps, schema: z.ZodType) {
  if (!isSameOriginJson(request)) {
    return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.crossSite, deps.correlationId());
  }
  const body = schema.safeParse(await readJsonBody(request));
  if (!body.success) return errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, deps.correlationId());
  const opened = open(rawId, request, deps);
  return opened instanceof Response ? opened : { ...opened, body: body.data as unknown };
}

export async function getProject(rawId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const opened = open(rawId, request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: `/projects/${opened.id}`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: ProjectSchema,
  });
}

export async function listPending(rawId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const search = new URL(request.url).searchParams;
  const query = PendingQuerySchema.safeParse({
    status: search.get("status") ?? undefined,
    limit: search.get("limit") ?? undefined,
    offset: search.get("offset") ?? undefined,
  });
  if (!query.success) return errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, deps.correlationId());
  const opened = open(rawId, request, deps);
  if (opened instanceof Response) return opened;

  // Query montada só com valores validados: nada do navegador é repassado cru.
  const params = new URLSearchParams({ limit: String(query.data.limit), offset: String(query.data.offset) });
  if (query.data.status) params.set("status", query.data.status);
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: `/projects/${opened.id}/pending?${params.toString()}`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: PendingPageSchema,
  });
}

export async function getDossier(rawId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const opened = open(rawId, request, deps);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "GET",
    path: `/projects/${opened.id}/dossier`,
    identity: opened.identity,
    okStatus: 200,
    okSchema: DossierSchema,
  });
}

/** Resposta humana a uma pendência. Quem pode responder (papel designado) é o backend que decide. */
export async function postAnswer(rawId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const opened = await openPost(rawId, request, deps, BffAnswerRequestSchema);
  if (opened instanceof Response) return opened;
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "POST",
    path: `/pending/${opened.id}/answer`,
    identity: opened.identity,
    body: opened.body,
    okStatus: 201,
    okSchema: PendingAnswerOutSchema,
    onConflict: stateConflict,
  });
}

/** Aprovação/rejeição FORMAL de artefato (ADR-0005): só gerente, conferido antes de chamar. */
export async function postApproval(rawId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const opened = await openPost(rawId, request, deps, BffApprovalRequestSchema);
  if (opened instanceof Response) return opened;
  if (opened.identity.role !== "manager") {
    return errorResponse(403, BffErrorCode.forbidden, "Só o gerente aprova ou rejeita artefatos.", opened.gate.cid);
  }
  return forward(deps, opened.gate, {
    ...ROUTE,
    method: "POST",
    path: `/artifacts/${opened.id}/approval`,
    identity: opened.identity,
    body: opened.body,
    okStatus: 201,
    okSchema: ApprovalSchema,
    onConflict: stateConflict,
  });
}

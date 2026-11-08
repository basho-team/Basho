import "server-only";
import { z } from "zod";
import { ApiReportVersionOutSchema, ApiReviewOutSchema } from "@/lib/api/reports";
import { BffErrorCode, BffReviewRequestSchema } from "@/lib/bff/contract";
import {
  COMMON_MESSAGES,
  defaultDeps,
  errorResponse,
  forward,
  identityFromPair,
  identityFromRole,
  isSameOriginJson,
  openGate,
  readJsonBody,
  type BffDeps,
  type RouteMessages,
} from "@/lib/server/bff-core";

export { IDENTITY_SECRET_HEADER, ROLE_HEADER, USER_ID_HEADER, type BffDeps } from "@/lib/server/bff-core";

const UuidSchema = z.uuid();
const BackendConflictSchema = z.object({ current_version_id: z.uuid() });

const MESSAGES: RouteMessages & { conflict: string } = {
  notFound: "Relatório não encontrado.",
  forbidden: "Este papel não pode revisar este relatório.",
  unavailable: "Revisão indisponível no momento. Avise a equipe técnica.",
  invalid: "A revisão ou correção não foi aceita para esta versão. Confira os campos.",
  conflict: "Esta versão não é mais a atual. Recarregue para ver a versão nova.",
};

const ROUTE = {
  unavailableCode: BffErrorCode.reviewUnavailable,
  invalidCode: BffErrorCode.invalidReview,
  messages: MESSAGES,
} as const;

function versionConflict(body: unknown, cid: string): Response {
  const conflict = BackendConflictSchema.safeParse(body);
  const extra = conflict.success ? { current_version_id: conflict.data.current_version_id } : undefined;
  return errorResponse(409, BffErrorCode.versionConflict, MESSAGES.conflict, cid, { extra });
}

/** GET de uma versão de relatório, com a identidade da sessão validada no servidor. */
export async function getReportVersion(rawVersionId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const cid = deps.correlationId();
  const versionId = UuidSchema.safeParse(rawVersionId);
  if (!versionId.success) return errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, cid);
  const gate = openGate(deps, cid, ROUTE.unavailableCode, MESSAGES.unavailable);
  if (gate instanceof Response) return gate;
  const identity = await identityFromRole(request, gate.env, deps);
  if (!identity) return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.noRole, cid);

  const response = await forward(deps, gate, {
    ...ROUTE,
    method: "GET",
    path: `/reports/${versionId.data}`,
    identity,
    okStatus: 200,
    okSchema: ApiReportVersionOutSchema,
  });
  if (response.ok && identity.role === "researcher") {
    const report = ApiReportVersionOutSchema.parse(await response.clone().json());
    if (report.version.draft.researcher_id !== identity.userId) {
      return errorResponse(403, BffErrorCode.forbidden, MESSAGES.forbidden, cid);
    }
  }
  return response;
}

/**
 * POST de revisão (ação formal, só humano — ADR-0005): recusa outra origem, valida corpo e
 * ID, aceita só o par (revisor, papel) da lista e injeta identidade e segredo no servidor.
 */
export async function postReview(rawVersionId: string, request: Request, deps: BffDeps = defaultDeps): Promise<Response> {
  const cid = deps.correlationId();
  if (!isSameOriginJson(request)) return errorResponse(403, BffErrorCode.forbidden, COMMON_MESSAGES.crossSite, cid);
  const versionId = UuidSchema.safeParse(rawVersionId);
  const body = BffReviewRequestSchema.safeParse(await readJsonBody(request));
  if (!versionId.success || !body.success) {
    return errorResponse(400, BffErrorCode.invalidRequest, COMMON_MESSAGES.invalidRequest, cid);
  }
  const gate = openGate(deps, cid, ROUTE.unavailableCode, MESSAGES.unavailable);
  if (gate instanceof Response) return gate;

  const { reviewer_id, role, ...review } = body.data;
  const identity = await identityFromPair(request, gate.env, reviewer_id, role, deps);
  if (!identity) return errorResponse(403, BffErrorCode.forbidden, MESSAGES.forbidden, cid);

  return forward(deps, gate, {
    ...ROUTE,
    method: "POST",
    path: `/reports/${versionId.data}/review`,
    identity,
    body: review,
    okStatus: 201,
    okSchema: ApiReviewOutSchema,
    onConflict: versionConflict,
  });
}

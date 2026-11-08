import { boundedJson } from "@/lib/auth/http";
import { authError, sameOriginJson, userFromRequest } from "@/lib/auth/session";
import { IntegrationActionSchema } from "@/lib/integrations/shared";
import { integrationAction, integrationOverview } from "@/lib/server/demo-integrations";
import { DataSourceError } from "@/lib/data/source";

export async function GET(request: Request): Promise<Response> {
  const user = await userFromRequest(request);
  if (!user) return authError(401, "Entre para continuar.");
  return Response.json(integrationOverview(user), { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request): Promise<Response> {
  if (!sameOriginJson(request)) return authError(403, "Origem da solicitação recusada.");
  const user = await userFromRequest(request);
  if (!user) return authError(401, "Entre para continuar.");
  const body = await boundedJson(request, 1024);
  if (body instanceof Response) return body;
  const parsed = IntegrationActionSchema.safeParse(body);
  if (!parsed.success) return authError(400, "Operação inválida.");
  try {
    return Response.json(integrationAction(user, parsed.data.provider, parsed.data.action), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof DataSourceError) return authError(error.error.code === "FORBIDDEN" ? 403 : 409, error.message);
    return authError(500, "Não foi possível verificar a prévia.");
  }
}

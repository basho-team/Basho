import { boundedJson } from "@/lib/auth/http";
import { authError, sameOriginJson, userFromRequest } from "@/lib/auth/session";
import { DemoRequestSchema, demoWorkspace, dispatchDemo } from "@/lib/server/demo-dispatch";
import { DataSourceError } from "@/lib/data/source";

export async function POST(request: Request): Promise<Response> {
  if (!sameOriginJson(request)) return authError(403, "Origem da solicitação recusada.");
  const user = await userFromRequest(request);
  if (!user) return authError(401, "Entre para continuar.");
  const body = await boundedJson(request, 16384);
  if (body instanceof Response) return body;
  const parsed = DemoRequestSchema.safeParse(body);
  if (!parsed.success) return authError(400, "Operação ou dados inválidos.");
  try {
    const result = await dispatchDemo(user, parsed.data, demoWorkspace());
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof DataSourceError) {
      const status = error.error.code === "FORBIDDEN" ? 403 : error.error.code === "NOT_FOUND" ? 404 : 409;
      return Response.json({ code: error.error.code, message: error.message }, { status, headers: { "Cache-Control": "no-store" } });
    }
    return authError(500, "Não foi possível concluir a operação.");
  }
}

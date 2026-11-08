import { authError, userFromRequest } from "@/lib/auth/session";

export async function GET(request: Request): Promise<Response> {
  const user = await userFromRequest(request);
  return user
    ? Response.json({ user }, { headers: { "Cache-Control": "no-store" } })
    : authError(401, "Entre para continuar.");
}

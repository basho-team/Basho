import { accountUser, DEMO_ACCOUNTS, type DemoUser } from "@/lib/auth/shared";
import { MANAGER_ID, RESEARCHER_ID } from "@/test/api-fixtures";

/** Apenas testes: a sessão verificada é injetada, sem interpretar headers de papel em produção. */
export async function testSession(request: Request): Promise<DemoUser | null> {
  const role = request.headers.get("X-Test-Session");
  if (role !== "researcher" && role !== "manager") return null;
  const account = role === "researcher" ? DEMO_ACCOUNTS[0] : DEMO_ACCOUNTS[2];
  return { ...accountUser(account), backendUserId: role === "researcher" ? RESEARCHER_ID : MANAGER_ID };
}

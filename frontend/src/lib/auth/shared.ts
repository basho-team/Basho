import { z } from "zod";

export const RoleSchema = z.enum(["researcher", "manager", "fiscal"]);
export type AppRole = z.infer<typeof RoleSchema>;

export const ROLE_LABELS: Record<AppRole, string> = {
  researcher: "Pesquisador",
  manager: "Gerente de projetos",
  fiscal: "Fiscal",
};

export const ROLE_HOME: Record<AppRole, string> = {
  researcher: "/pesquisador",
  manager: "/gerente",
  fiscal: "/fiscal",
};

/** Contas e organização inteiramente fictícias; não são cadastro de produção. */
export const DEMO_ACCOUNTS = [
  { id: "ana", personId: "p-ana", email: "ana@lumen.example", name: "Ana Ribeiro", role: "researcher" },
  { id: "bruno", personId: "p-bruno", email: "bruno@lumen.example", name: "Bruno Costa", role: "researcher" },
  { id: "marina", personId: "p-marina", email: "marina@lumen.example", name: "Marina Duarte", role: "manager" },
  { id: "rafael", personId: "p-rafael", email: "rafael@lumen.example", name: "Rafael Lima", role: "fiscal" },
] as const;

export interface DemoUser {
  accountId: string;
  personId: string;
  email: string;
  name: string;
  role: AppRole;
  backendUserId?: string;
  organizationId: "org-lumen";
  organizationName: string;
}

export function accountUser(account: (typeof DEMO_ACCOUNTS)[number]): DemoUser {
  return {
    accountId: account.id,
    personId: account.personId,
    email: account.email,
    name: account.name,
    role: account.role,
    organizationId: "org-lumen",
    organizationName: "Lumen Sensores (demonstração)",
  };
}

export function mayVisit(role: AppRole, pathname: string): boolean {
  const prefix = pathname.split("/")[1];
  if (prefix === "pesquisador") return role === "researcher";
  if (prefix === "gerente") return role === "manager";
  if (prefix === "fiscal") return role === "fiscal";
  return ["/", "/integracoes", "/acesso-negado"].includes(pathname);
}

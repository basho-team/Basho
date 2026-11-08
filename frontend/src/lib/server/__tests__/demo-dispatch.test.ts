import { describe, expect, test } from "vitest";
import { accountUser, DEMO_ACCOUNTS } from "@/lib/auth/shared";
import { createMockSource } from "@/lib/data/mock-source";
import { DemoRequestSchema, dispatchDemo } from "@/lib/server/demo-dispatch";
import { integrationAction, integrationOverview } from "@/lib/server/demo-integrations";

const ana = accountUser(DEMO_ACCOUNTS[0]);
const bruno = accountUser(DEMO_ACCOUNTS[1]);
const manager = accountUser(DEMO_ACCOUNTS[2]);
const fiscal = accountUser(DEMO_ACCOUNTS[3]);

function source() { return createMockSource({ latencyMs: 0 }); }
function request(operation: string, args: unknown[]) { return DemoRequestSchema.parse({ operation, args }); }

describe("operações sintéticas com autorização no servidor", () => {
  test("Ana vê apenas seus relatórios e não lê o de Bruno por ID", async () => {
    const data = source();
    const reports = await dispatchDemo(ana, request("listReports", ["per-2026-10"]), data);
    expect(reports).toEqual(expect.arrayContaining([expect.objectContaining({ author_id: "p-ana" })]));
    expect(JSON.stringify(reports)).not.toContain("p-bruno");
    await expect(dispatchDemo(ana, request("getReport", ["rep-bruno", null]), data)).rejects.toThrow("Sua função");
  });
  test("não é possível aprovar outra pessoa ou assumir papel de gerente", async () => {
    const data = source();
    await expect(dispatchDemo(ana, request("submitReview", [{
      reportVersionId: "rv-bruno-2", reviewerId: "p-ana", role: "researcher", decision: "approve", justification: "Conferido",
    }]), data)).rejects.toThrow("Sua função");
    await expect(dispatchDemo(ana, request("triggerClosing", ["per-2026-10"]), data)).rejects.toThrow("Sua função");
    await expect(dispatchDemo(ana, request("submitReview", [{
      reportVersionId: "rv-ana-1", reviewerId: "p-marina", role: "manager", decision: "approve", justification: "Conferido",
    }]), data)).rejects.toThrow("Sua função");
  });
  test("gerente lê a consolidação e fiscal lê o pacote, com operações separadas", async () => {
    const data = source();
    expect(await dispatchDemo(manager, request("getConsolidation", ["per-2026-10"]), data)).toHaveProperty("reports");
    expect(await dispatchDemo(fiscal, request("getFiscalPackage", ["per-2026-10"]), data)).toHaveProperty("findings");
    await expect(dispatchDemo(fiscal, request("triggerClosing", ["per-2026-10"]), data)).rejects.toThrow();
    await expect(dispatchDemo(manager, request("recordFiscalDecision", [{
      findingId: "f1", decidedBy: "p-rafael", decision: "agree", note: "Conferido",
    }]), data)).rejects.toThrow();
  });
  test("aprovação própria preserva conflito de versão e a decisão anterior", async () => {
    const data = source();
    const detail = await data.getReport("rep-ana");
    const approve = request("submitReview", [{ reportVersionId: detail.version.id, reviewerId: ana.personId,
      role: ana.role, decision: "approve", justification: "Conferido com a fonte" }]);
    await dispatchDemo(ana, approve, data);
    const claim = detail.version.claims[0];
    await dispatchDemo(ana, request("submitCorrection", [{ reportVersionId: detail.version.id, reviewerId: ana.personId,
      role: ana.role, claimId: claim.id, newText: claim.text + " Texto corrigido.", justification: "Corrigir esta versão" }]), data);
    await expect(dispatchDemo(ana, approve, data)).rejects.toThrow();
  });
  test("entrada desconhecida e payload com campos extras são recusados", () => {
    expect(DemoRequestSchema.safeParse({ operation: "__proto__", args: [] }).success).toBe(false);
    expect(DemoRequestSchema.safeParse({ operation: "getContext", args: [], role: "manager" }).success).toBe(false);
  });
});

describe("GitHub, Notion e Drive por função", () => {
  test.each(["github", "notion", "drive"] as const)("%s: prévia legível, sintética e limitada ao pesquisador", provider => {
    for (const user of [ana, bruno, manager, fiscal]) {
      const result = integrationAction(user, provider, "verify");
      const integration = result.integrations.find(item => item.provider === provider)!;
      expect(integration.sources.length).toBeGreaterThan(0);
      expect(integration.checkedAt).not.toBeNull();
      expect(integration.sources.every(item => item.isSynthetic)).toBe(true);
      if (user.role === "researcher") expect(integration.sources.every(item => item.ownerId === user.personId)).toBe(true);
    }
  });
  test.each(["github", "notion", "drive"] as const)("%s: configuração é do gerente, inclusive na API", provider => {
    expect(() => integrationAction(ana, provider, "disable")).toThrow();
    expect(() => integrationAction(fiscal, provider, "sync")).toThrow();
    integrationAction(manager, provider, "disable");
    expect(() => integrationAction(bruno, provider, "verify")).toThrow();
    integrationAction(manager, provider, "enable");
    expect(integrationOverview(ana).integrations.find(item => item.provider === provider)?.enabled).toBe(true);
  });
});

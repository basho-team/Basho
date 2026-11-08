import { beforeEach, describe, expect, test } from "vitest";
import { createMockSource } from "@/lib/data/mock-source";
import { RUN_RUNNING_MS } from "@/lib/data/mock-state";
import { DataSourceError, type DataSource } from "@/lib/data/source";

const PERIOD_ID = "per-2026-10";

let clock = 0;
let failing: string[] = [];
let source: DataSource;

beforeEach(() => {
  clock = Date.parse("2026-11-07T12:00:00Z");
  failing = [];
  source = createMockSource({ now: () => clock, latencyMs: 0, failures: () => failing });
});

async function errorCode(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof DataSourceError) return error.error.code;
    throw error;
  }
  throw new Error("esperava erro");
}

async function approveAna(): Promise<void> {
  const report = await source.getReport("rep-ana");
  await source.submitReview({
    reportVersionId: report.version.id,
    reviewerId: "p-ana",
    role: "researcher",
    decision: "approve",
    justification: "Confere.",
  });
}

describe("mock-source: revisões versionadas", () => {
  test("revisar versão antiga retorna VERSION_CONFLICT", async () => {
    // Arrange
    const old = await source.getReport("rep-bruno", 1);

    // Act
    const code = await errorCode(
      source.submitReview({
        reportVersionId: old.version.id,
        reviewerId: "p-bruno",
        role: "researcher",
        decision: "approve",
        justification: "ok",
      }),
    );

    // Assert
    expect(code).toBe("VERSION_CONFLICT");
  });

  test("correção cria versão N+1 sem herdar a aprovação anterior", async () => {
    // Arrange
    const v2 = await source.getReport("rep-bruno");
    const claimId = v2.version.claims[0].id;

    // Act
    const v3 = await source.submitCorrection({
      reportVersionId: v2.version.id,
      reviewerId: "p-bruno",
      role: "researcher",
      claimId,
      newText: "Integrou a coleta das bancadas B e C.",
      justification: "Faltou a bancada C.",
    });
    const reports = await source.listReports(PERIOD_ID);

    // Assert
    expect(v3.version.version).toBe(3);
    expect(v3.reviews).toEqual([]);
    expect(v3.version.review_state).toBe("awaiting_researcher");
    expect(reports.find((r) => r.report_id === "rep-bruno")?.approved_by_researcher).toBe(false);
  });

  test("pesquisador não aprova relatório de outra pessoa", async () => {
    // Arrange
    const report = await source.getReport("rep-ana");

    // Act
    const code = await errorCode(
      source.submitReview({
        reportVersionId: report.version.id,
        reviewerId: "p-bruno",
        role: "researcher",
        decision: "approve",
        justification: "ok",
      }),
    );

    // Assert
    expect(code).toBe("FORBIDDEN");
  });
});

describe("mock-source: consolidação e encaminhamento", () => {
  test("encaminhar com relatório pendente é bloqueado e o motivo é exposto", async () => {
    // Arrange
    const consolidation = await source.getConsolidation(PERIOD_ID);

    // Act
    const code = await errorCode(source.forwardToFiscal(PERIOD_ID));

    // Assert
    expect(consolidation.can_forward).toBe(false);
    expect(consolidation.blocking_reasons.join(" ")).toContain("Ana Ribeiro");
    expect(code).toBe("FORWARD_BLOCKED");
  });

  test("após aprovações, encaminha snapshot e o pacote fiscal fica disponível", async () => {
    // Arrange
    await approveAna();

    // Act
    const consolidation = await source.forwardToFiscal(PERIOD_ID);
    const pkg = await source.getFiscalPackage(PERIOD_ID);

    // Assert
    expect(consolidation.forwarded_at).not.toBeNull();
    expect(pkg.available).toBe(true);
    expect(pkg.report_versions).toHaveLength(2);
    expect(pkg.stale).toBe(false);
  });
});

describe("mock-source: despesas, pendências e reanálise", () => {
  test("despesa sem valor permanece null e a duplicada fica excluída com motivo", async () => {
    // Arrange / Act
    const pkg = await source.getFiscalPackage(PERIOD_ID);
    const semValor = pkg.expenses.find((e) => e.id === "exp-calibracao");
    const duplicada = pkg.expenses.find((e) => e.id === "exp-boleto1023");

    // Assert
    expect(semValor?.amount).toBeNull();
    expect(duplicada?.reconciliation_state).toBe("excluded");
    expect(duplicada?.excluded_reason).toBeTruthy();
  });

  test("resposta à pendência gera nova versão do relatório e marca o pacote como desatualizado", async () => {
    // Arrange
    await approveAna();
    await source.forwardToFiscal(PERIOD_ID);
    const request = await source.returnPending({
      findingId: "f-horas-ana",
      assigneeRole: "researcher",
      reason: "Faltam horas.",
      evidenceNeeded: "Planilha de horas.",
    });

    // Act
    await source.respondPending({ requestId: request.id, respondedBy: "p-ana", response: "40 h (planilha de outubro)." });
    const during = await source.getFiscalPackage(PERIOD_ID);
    clock += RUN_RUNNING_MS + 1;
    const after = await source.getFiscalPackage(PERIOD_ID);
    const report = await source.getReport("rep-ana");

    // Assert
    expect(during.findings.find((f) => f.id === "f-horas-ana")?.awaiting_reanalysis).toBe(true);
    expect(after.findings.find((f) => f.id === "f-horas-ana")?.awaiting_reanalysis).toBe(false);
    expect(report.version.version).toBe(2);
    expect(report.version.gaps).toEqual([]);
    expect(report.reviews).toEqual([]);
    expect(after.stale).toBe(true);
  });

  test("resposta sobre a nota mista não a torna elegível por inteiro", async () => {
    // Arrange
    const request = await source.returnPending({
      findingId: "f-desp-nf1023",
      assigneeRole: "manager",
      reason: "Falta critério de alocação.",
      evidenceNeeded: "Critério e documento.",
    });

    // Act
    await source.respondPending({ requestId: request.id, respondedBy: "p-marina", response: "70% P&D por uso medido." });
    clock += RUN_RUNNING_MS + 1;
    const pkg = await source.getFiscalPackage(PERIOD_ID);
    const finding = pkg.findings.find((f) => f.id === "f-desp-nf1023");

    // Assert
    expect(finding?.signal).toBe("fiscal_judgment_required");
    expect(finding?.signal).not.toBe("supported_by_evidence");
  });

  test("pendência já respondida não aceita segunda resposta", async () => {
    // Arrange
    const request = await source.requestClarification({ reportId: "rep-bruno", question: "Qual bancada?" });
    await source.respondPending({ requestId: request.id, respondedBy: "p-bruno", response: "B." });

    // Act
    const code = await errorCode(
      source.respondPending({ requestId: request.id, respondedBy: "p-bruno", response: "B de novo." }),
    );

    // Assert
    expect(code).toBe("REQUEST_NOT_OPEN");
  });

  test("falha injetada é recuperável e não altera o estado", async () => {
    // Arrange
    failing = ["triggerClosing"];

    // Act
    const code = await errorCode(source.triggerClosing(PERIOD_ID));
    failing = [];
    const consolidation = await source.getConsolidation(PERIOD_ID);

    // Assert
    expect(code).toBe("SIMULATED_FAILURE");
    expect(consolidation.last_run).toBeNull();
  });
});

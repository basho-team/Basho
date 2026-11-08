import { beforeEach, describe, expect, test, vi } from "vitest";
import { createApiSource } from "@/lib/data/api-source";
import { DataSourceError, type DataSource } from "@/lib/data/source";
import { jsonResponse } from "@/test/api-fixtures";
import {
  ARTIFACT_ID,
  approvalOut,
  dossierOut,
  PENDING_APPROVAL_ID,
  PENDING_OPEN_ID,
  pendingItem,
  PROJECT_ID,
} from "@/test/project-fixtures";

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
let role: "researcher" | "manager" | null;
let source: DataSource;

beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>();
  role = "researcher";
  source = createApiSource({ fetch: fetchMock, projectId: PROJECT_ID, currentRole: () => role });
});

async function caught(promise: Promise<unknown>): Promise<DataSourceError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof DataSourceError) return error;
    throw error;
  }
  throw new Error("esperava erro");
}

function header(index: number, name: string): string | null {
  return new Headers(fetchMock.mock.calls[index]?.[1]?.headers).get(name);
}

describe("api-source: pendências (#5)", () => {
  test("lista as do papel, percorrendo páginas, e declara o papel ao BFF", async () => {
    // Arrange
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ items: [pendingItem(PENDING_OPEN_ID), pendingItem("77777777-0000-4000-8000-00000000000a", { assignee: "manager" })], next_offset: 200 }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ items: [pendingItem("77777777-0000-4000-8000-00000000000b", { status: "resolved" })], next_offset: null }),
      );

    // Act
    const pending = await source.listPendingFor("researcher");

    // Assert
    expect(pending.map((p) => p.id)).toEqual([PENDING_OPEN_ID]);
    expect(pending[0]).toMatchObject({
      target: { type: "artifact", id: ARTIFACT_ID },
      reason: "Quantas horas formais foram declaradas para esta atividade?",
      requested_by_role: null,
      kind: "missing_justification",
    });
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`/api/bff/projects/${PROJECT_ID}/pending?limit=200&offset=200`);
    expect(header(0, "X-Demo-Role")).toBe("researcher");
    expect(header(0, "X-Basho-Identity-Secret")).toBeNull();
  });

  test("assignee_role desconhecido é descartado, não adivinhado", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ items: [pendingItem(PENDING_OPEN_ID, { assignee: "financeiro" })], next_offset: null }));

    // Act
    const pending = await source.listPendingFor("researcher");

    // Assert
    expect(pending).toEqual([]);
  });

  test("responder envia só o texto e devolve a pendência respondida", async () => {
    // Arrange
    fetchMock.mockResolvedValue(
      jsonResponse({ pending: { ...pendingItem(PENDING_OPEN_ID, { status: "answered" }), response: "12 horas." }, correction_event_id: ARTIFACT_ID }, 201),
    );

    // Act
    const answered = await source.respondPending({ requestId: PENDING_OPEN_ID, respondedBy: "ignorado", response: "12 horas." });

    // Assert
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ answer: "12 horas." });
    expect(answered).toMatchObject({ status: "answered", response: "12 horas." });
  });

  test("409 de pendência encerrada chega à UI como STATE_CONFLICT", async () => {
    // Arrange
    fetchMock.mockResolvedValue(
      jsonResponse({ code: "STATE_CONFLICT", message: "Esta pendência já foi respondida.", correlation_id: "bff-1", retryable: false, reason: "pending_closed" }, 409),
    );

    // Act
    const error = await caught(source.respondPending({ requestId: PENDING_OPEN_ID, respondedBy: "x", response: "ok" }));

    // Assert
    expect(error.error.code).toBe("STATE_CONFLICT");
  });

  test("sem projeto configurado, falha explícita sem chamar o BFF", async () => {
    // Arrange
    source = createApiSource({ fetch: fetchMock, currentRole: () => role });

    // Act
    const error = await caught(source.listPendingFor("manager"));

    // Assert
    expect(error.error.code).toBe("NOT_CONFIGURED");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("api-source: aprovação formal e dossiê (#5, #13)", () => {
  test("gerente decide o artefato da pendência de aprovação", async () => {
    // Arrange
    role = "manager";
    fetchMock.mockResolvedValue(jsonResponse(approvalOut("reject"), 201));

    // Act
    const decision = await source.decideArtifact({ artifactId: ARTIFACT_ID, decision: "reject", comment: "Sem fonte para a bancada C." });

    // Assert
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/artifacts/${ARTIFACT_ID}/approval`);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ decision: "reject", comment: "Sem fonte para a bancada C." });
    expect(header(0, "X-Demo-Role")).toBe("manager");
    expect(decision).toMatchObject({ decision: "reject", status: "rejected" });
  });

  test("dossiê é validado e chega no formato do contrato", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse(dossierOut()));

    // Act
    const dossier = await source.getDossier();

    // Assert
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/projects/${PROJECT_ID}/dossier`);
    expect(dossier.entries.map((e) => e.status)).toEqual(["approved", "needs_review"]);
    expect(dossier.entries[1]?.history[1]?.supersedes).toBe(dossier.entries[1]?.artifact_id);
  });

  test("pendência de aprovação mantém o kind para a UI mostrar a decisão formal", async () => {
    // Arrange
    role = "manager";
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [pendingItem(PENDING_APPROVAL_ID, { kind: "approval_required", assignee: "manager" })], next_offset: null }),
    );

    // Act
    const [item] = await source.listPendingFor("manager");

    // Assert
    expect(item).toMatchObject({ kind: "approval_required", target: { id: ARTIFACT_ID } });
  });
});

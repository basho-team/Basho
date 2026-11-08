import { beforeEach, describe, expect, test, vi } from "vitest";
import { createApiSource } from "@/lib/data/api-source";
import { DataSourceError, type DataSource } from "@/lib/data/source";
import {
  CLAIM_ID,
  EVIDENCE_ID,
  jsonResponse,
  RESEARCHER_ID,
  reviewOut,
  twoVersionSeries,
  V1_ID,
  V2_ID,
  versionOut,
} from "@/test/api-fixtures";

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
let source: DataSource;
let series: ReturnType<typeof twoVersionSeries>;

/** BFF simulado: GET devolve a série; POST usa a resposta configurada no teste. */
function routeBff(post: () => Response) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return post();
    const id = url.split("/").pop() ?? "";
    const out = series[id];
    return out ? jsonResponse(out) : jsonResponse({ code: "NOT_FOUND", message: "x", correlation_id: "c", retryable: false }, 404);
  });
}

beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>();
  source = createApiSource({ fetch: fetchMock });
  series = twoVersionSeries();
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

describe("api-source: relatório", () => {
  test("a partir de uma versão antiga, carrega a série e mostra a atual", async () => {
    // Arrange
    routeBff(() => jsonResponse({}, 500));

    // Act
    const detail = await source.getReport(V1_ID);

    // Assert
    expect(detail.version.id).toBe(V2_ID);
    expect(detail.latest_version).toBe(2);
    expect(detail.history.map((h) => h.version)).toEqual([1, 2]);
    expect(detail.period_label).toBe("01/10/2026 a 31/10/2026");
    expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith("/api/bff/"))).toBe(true);
  });

  test("mapeia afirmações, lacunas e evidências citadas sem inventar conteúdo", async () => {
    // Arrange
    routeBff(() => jsonResponse({}, 500));

    // Act
    const { version, evidence } = await source.getReport(V2_ID);

    // Assert
    expect(version.claims[0]).toMatchObject({ id: CLAIM_ID, section: "method", evidence_ids: [EVIDENCE_ID], corrected_by_human: true, justification: null });
    expect(version.claims[1]).toMatchObject({ status: "pending", justification: "Qual foi o erro medido na calibração?" });
    expect(version.gaps[0]?.question).toBe("Quantas horas formais foram declaradas?");
    expect(version.author_id).toBe(RESEARCHER_ID);
    expect(version.review_state).toBe("awaiting_researcher");
    expect(evidence).toEqual([]);
  });

  test("versão antiga pedida por número aparece como substituída", async () => {
    // Arrange
    routeBff(() => jsonResponse({}, 500));

    // Act
    const detail = await source.getReport(V2_ID, 1);

    // Assert
    expect(detail.version.id).toBe(V1_ID);
    expect(detail.version.review_state).toBe("superseded");
    expect(detail.reviews).toEqual([]);
  });

  test("estado por papel vem do backend: pesquisador aprovou, aguarda gerente", async () => {
    // Arrange
    series[V2_ID] = versionOut({ id: V2_ID, number: 2, supersedesId: V1_ID, currentId: V2_ID, currentNumber: 2, researcher: "text_approved" });
    routeBff(() => jsonResponse({}, 500));

    // Act
    const detail = await source.getReport(V2_ID);

    // Assert
    expect(detail.version.review_state).toBe("awaiting_manager");
    expect(detail.reviews).toEqual([expect.objectContaining({ role: "researcher", decision: "approve", justification: null })]);
  });

  test("resposta fora do contrato vira INVALID_RESPONSE", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ version: { id: "x" } }));

    // Act
    const error = await caught(source.getReport(V2_ID));

    // Assert
    expect(error.error.code).toBe("INVALID_RESPONSE");
  });
});

describe("api-source: revisão", () => {
  test("aprova a versão exata enviando só identidade da demo, sem segredo", async () => {
    // Arrange
    routeBff(() => jsonResponse(reviewOut(V2_ID, "text_approved"), 201));

    // Act
    const review = await source.submitReview({
      reportVersionId: V2_ID,
      reviewerId: RESEARCHER_ID,
      role: "researcher",
      decision: "approve",
      justification: "Confere com o diário.",
    });

    // Assert
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe(`/api/bff/reports/${V2_ID}/review`);
    expect(JSON.parse(String(init?.body))).toEqual({
      reviewer_id: RESEARCHER_ID,
      role: "researcher",
      decision: "text_approved",
      comment: "Confere com o diário.",
    });
    expect(new Headers(init?.headers).has("X-Basho-Identity-Secret")).toBe(false);
    expect(review).toMatchObject({ report_version_id: V2_ID, decision: "approve", role: "researcher" });
  });

  test.each([
    [409, "VERSION_CONFLICT"],
    [503, "REVIEW_UNAVAILABLE"],
  ])("erro %i do BFF chega à UI como %s", async (status, code) => {
    // Arrange
    routeBff(() => jsonResponse({ code, message: "mensagem do BFF", correlation_id: "bff-1", retryable: false }, status));

    // Act
    const error = await caught(
      source.submitReview({ reportVersionId: V1_ID, reviewerId: RESEARCHER_ID, role: "researcher", decision: "approve", justification: "Ok." }),
    );

    // Assert
    expect(error.error).toMatchObject({ code, correlation_id: "bff-1" });
  });

  test("fiscal não revisa relatório e nada é enviado", async () => {
    // Act
    const error = await caught(
      source.submitReview({ reportVersionId: V2_ID, reviewerId: RESEARCHER_ID, role: "fiscal", decision: "approve", justification: "Ok." }),
    );

    // Assert
    expect(error.error.code).toBe("FORBIDDEN");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("correção vira changes_requested com revise_claim preservando status e evidências", async () => {
    // Arrange
    routeBff(() => jsonResponse(reviewOut(V2_ID, "changes_requested"), 201));

    // Act
    await source.submitCorrection({
      reportVersionId: V2_ID,
      reviewerId: RESEARCHER_ID,
      role: "researcher",
      claimId: CLAIM_ID,
      newText: "Integrou a coleta das bancadas B e C.",
      justification: "Faltou a bancada C no texto.",
    });

    // Assert
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      reviewer_id: RESEARCHER_ID,
      role: "researcher",
      decision: "changes_requested",
      comment: null,
      correction: {
        reason: "Faltou a bancada C no texto.",
        operations: [
          {
            kind: "revise_claim",
            claim_id: CLAIM_ID,
            text: "Integrou a coleta das bancadas B e C.",
            status: "supported",
            evidence_ids: [EVIDENCE_ID],
            question: null,
            ask_role: null,
            dispute_reason: null,
          },
        ],
      },
    });
  });

  test("operações sem contrato publicado continuam explícitas", async () => {
    // Act
    const error = await caught(source.getConsolidation("per-1"));

    // Assert
    expect(error.error.code).toBe("NOT_IMPLEMENTED");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

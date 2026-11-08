import { beforeEach, describe, expect, test, vi } from "vitest";
import { readServerEnv, ServerConfigError, type ServerEnv } from "@/lib/server/env";
import {
  getReportVersion,
  IDENTITY_SECRET_HEADER,
  postReview,
  ROLE_HEADER,
  USER_ID_HEADER,
  type BffDeps,
} from "@/lib/server/reports-bff";
import { jsonResponse, MANAGER_ID, RESEARCHER_ID, reviewOut, V1_ID, V2_ID, versionOut } from "@/test/api-fixtures";

const SECRET = "s".repeat(40);
const BACKEND = "http://backend.test";

let env: ServerEnv;
let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
let deps: BffDeps;

beforeEach(() => {
  env = {
    backendUrl: BACKEND,
    reviewerIdentitySecret: SECRET,
    demoReviewers: [
      { userId: RESEARCHER_ID, role: "researcher" },
      { userId: MANAGER_ID, role: "manager" },
    ],
  };
  fetchMock = vi.fn<typeof fetch>();
  deps = { env: () => env, fetch: fetchMock, correlationId: () => "bff-test" };
});

function reviewRequest(body: unknown): Request {
  return new Request("http://bff.test/api/bff/reports/x/review", { method: "POST", body: JSON.stringify(body) });
}

const approve = { reviewer_id: RESEARCHER_ID, role: "researcher", decision: "text_approved", comment: "Confere." };

function sentHeaders(): Headers {
  return new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
}

describe("BFF GET /reports/{id}", () => {
  test("repassa a versão sem headers de identidade nem segredo", async () => {
    // Arrange
    const body = versionOut({ id: V2_ID, number: 2, supersedesId: V1_ID, currentId: V2_ID, currentNumber: 2 });
    fetchMock.mockResolvedValue(jsonResponse(body));

    // Act
    const res = await getReportVersion(V2_ID, deps);

    // Assert
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(body);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${BACKEND}/api/v1/reports/${V2_ID}`);
    expect(sentHeaders().has(IDENTITY_SECRET_HEADER)).toBe(false);
  });

  test("ID que não é UUID devolve 400 sem chamar o backend", async () => {
    // Act
    const res = await getReportVersion("../../health", deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("backend fora do ar vira 502 recuperável", async () => {
    // Arrange
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    // Act
    const res = await getReportVersion(V2_ID, deps);

    // Assert
    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({ code: "BACKEND_UNAVAILABLE", retryable: true, correlation_id: "bff-test" });
  });
});

describe("BFF POST /reports/{id}/review", () => {
  test("injeta identidade e segredo só na chamada ao backend e não repassa reviewer_id/role no corpo", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse(reviewOut(V2_ID, "text_approved"), 201));

    // Act
    const res = await postReview(V2_ID, reviewRequest(approve), deps);

    // Assert
    expect(res.status).toBe(201);
    const headers = sentHeaders();
    expect(headers.get(USER_ID_HEADER)).toBe(RESEARCHER_ID);
    expect(headers.get(ROLE_HEADER)).toBe("researcher");
    expect(headers.get(IDENTITY_SECRET_HEADER)).toBe(SECRET);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ decision: "text_approved", comment: "Confere." });
    expect(JSON.stringify(await res.json())).not.toContain(SECRET);
  });

  test("sem segredo configurado devolve 503 sem chamar o backend", async () => {
    // Arrange
    env = { ...env, reviewerIdentitySecret: null };

    // Act
    const res = await postReview(V2_ID, reviewRequest(approve), deps);

    // Assert
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ code: "REVIEW_UNAVAILABLE", retryable: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test.each([
    ["revisor fora da lista", { ...approve, reviewer_id: "33333333-3333-4333-8333-333333333333" }],
    ["papel diferente do configurado", { ...approve, reviewer_id: MANAGER_ID }],
  ])("%s devolve 403 sem chamar o backend", async (_label, body) => {
    // Act
    const res = await postReview(V2_ID, reviewRequest(body), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test.each([
    ["campo extra", { ...approve, identity_secret: "x" }],
    ["papel fiscal", { ...approve, role: "fiscal" }],
    ["operação de correção não suportada", { ...approve, decision: "changes_requested", correction: { reason: "Motivo longo o bastante.", operations: [{ kind: "withdraw_claim" }] } }],
  ])("corpo inválido (%s) devolve 400", async (_label, body) => {
    // Act
    const res = await postReview(V2_ID, reviewRequest(body), deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("409 do backend vira VERSION_CONFLICT com a versão atual", async () => {
    // Arrange
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "a versão revisada não é a atual", requested_version_id: V1_ID, current_version_id: V2_ID }, 409),
    );

    // Act
    const res = await postReview(V1_ID, reviewRequest(approve), deps);

    // Assert
    expect(res.status).toBe(409);
    expect(await res.json()).toMatchObject({ code: "VERSION_CONFLICT", current_version_id: V2_ID });
  });

  test.each([
    [503, 503, "REVIEW_UNAVAILABLE"],
    [401, 503, "REVIEW_UNAVAILABLE"],
    [403, 403, "FORBIDDEN"],
    [422, 422, "INVALID_REVIEW"],
    [500, 502, "BACKEND_UNAVAILABLE"],
  ])("backend %i vira %i %s sem vazar o detalhe do backend", async (backendStatus, status, code) => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "detalhe interno do backend" }, backendStatus));

    // Act
    const res = await postReview(V2_ID, reviewRequest(approve), deps);

    // Assert
    expect(res.status).toBe(status);
    const body = await res.json();
    expect(body.code).toBe(code);
    expect(JSON.stringify(body)).not.toContain("detalhe interno");
  });
});

describe("configuração do servidor", () => {
  test("lê revisores e segredo das variáveis sem NEXT_PUBLIC_", () => {
    // Act
    const parsed = readServerEnv({
      REVIEWER_IDENTITY_SECRET: SECRET,
      BASHO_DEMO_REVIEWERS: `${RESEARCHER_ID}:researcher, ${MANAGER_ID}:manager`,
      BASHO_API_URL: "http://api.local:8000/",
    });

    // Assert
    expect(parsed.backendUrl).toBe("http://api.local:8000");
    expect(parsed.demoReviewers).toEqual([
      { userId: RESEARCHER_ID, role: "researcher" },
      { userId: MANAGER_ID, role: "manager" },
    ]);
  });

  test("segredo vazio conta como não configurado", () => {
    expect(readServerEnv({}).reviewerIdentitySecret).toBeNull();
  });

  test.each([
    { REVIEWER_IDENTITY_SECRET: "curto" },
    { BASHO_DEMO_REVIEWERS: "nao-e-uuid:researcher" },
    { BASHO_DEMO_REVIEWERS: `${RESEARCHER_ID}:fiscal` },
  ])("configuração inválida falha sem expor o valor (%o)", (source) => {
    expect(() => readServerEnv(source)).toThrow(ServerConfigError);
  });
});

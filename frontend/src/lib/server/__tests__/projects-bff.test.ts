import { beforeEach, describe, expect, test, vi } from "vitest";
import { IDENTITY_SECRET_HEADER, ROLE_HEADER, USER_ID_HEADER, type BffDeps } from "@/lib/server/bff-core";
import type { ServerEnv } from "@/lib/server/env";
import { getDossier, getProject, listPending, postAnswer, postApproval } from "@/lib/server/projects-bff";
import { jsonResponse, MANAGER_ID, RESEARCHER_ID } from "@/test/api-fixtures";
import { ARTIFACT_ID, approvalOut, dossierOut, PENDING_OPEN_ID, pendingItem, PROJECT_ID } from "@/test/project-fixtures";

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

function get(url: string, role = "manager"): Request {
  return new Request(url, { headers: { "X-Demo-Role": role } });
}

function post(body: unknown, role = "researcher", headers: Record<string, string> = {}): Request {
  return new Request("http://bff.test/api/bff/x", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", Origin: "http://bff.test", "X-Demo-Role": role, ...headers },
  });
}

function sent(index = 0): { url: string; headers: Headers; body: unknown } {
  const [url, init] = fetchMock.mock.calls[index] ?? [];
  return { url: String(url), headers: new Headers(init?.headers), body: init?.body ? JSON.parse(String(init.body)) : undefined };
}

describe("BFF: leituras de projeto com identidade", () => {
  test("dossiê vai com identidade do papel e volta só com campos do contrato", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ ...dossierOut(), internal: "x" }));

    // Act
    const res = await getDossier(PROJECT_ID, get("http://bff.test/api/bff/projects/p/dossier"), deps);

    // Assert
    expect(res.status).toBe(200);
    const call = sent();
    expect(call.url).toBe(`${BACKEND}/api/v1/projects/${PROJECT_ID}/dossier`);
    expect(call.headers.get(USER_ID_HEADER)).toBe(MANAGER_ID);
    expect(call.headers.get(ROLE_HEADER)).toBe("manager");
    expect(call.headers.get(IDENTITY_SECRET_HEADER)).toBe(SECRET);
    expect(JSON.stringify(await res.json())).not.toContain("internal");
  });

  test("pendências repassam só query validada", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ items: [pendingItem(PENDING_OPEN_ID)], next_offset: null }));

    // Act
    const res = await listPending(
      PROJECT_ID,
      get("http://bff.test/api/bff/projects/p/pending?status=open&limit=200&offset=0&evil=1"),
      deps,
    );

    // Assert
    expect(res.status).toBe(200);
    expect(sent().url).toBe(`${BACKEND}/api/v1/projects/${PROJECT_ID}/pending?limit=200&offset=0&status=open`);
  });

  test.each([
    ["limite acima do máximo", "limit=500"],
    ["status inventado", "status=deleted"],
    ["offset negativo", "offset=-1"],
  ])("query inválida (%s) devolve 400 sem chamar o backend", async (_label, query) => {
    // Act
    const res = await listPending(PROJECT_ID, get(`http://bff.test/x?${query}`), deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("projeto: ID inválido → 400; sem papel → 403; 413 do backend → TOO_LARGE", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "x" }, 413));

    // Act
    const badId = await getProject("nao-uuid", get("http://bff.test/x"), deps);
    const noRole = await getProject(PROJECT_ID, get("http://bff.test/x", ""), deps);
    const tooLarge = await getProject(PROJECT_ID, get("http://bff.test/x"), deps);

    // Assert
    expect(badId.status).toBe(400);
    expect(noRole.status).toBe(403);
    expect(await tooLarge.json()).toMatchObject({ code: "TOO_LARGE" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("BFF: resposta a pendência", () => {
  test("repassa só o texto, com a identidade do papel declarado", async () => {
    // Arrange
    fetchMock.mockResolvedValue(
      jsonResponse({ pending: pendingItem(PENDING_OPEN_ID, { status: "answered" }), correction_event_id: ARTIFACT_ID }, 201),
    );

    // Act
    const res = await postAnswer(PENDING_OPEN_ID, post({ answer: "12 horas, planilha de outubro." }), deps);

    // Assert
    expect(res.status).toBe(201);
    const call = sent();
    expect(call.url).toBe(`${BACKEND}/api/v1/pending/${PENDING_OPEN_ID}/answer`);
    expect(call.body).toEqual({ answer: "12 horas, planilha de outubro." });
    expect(call.headers.get(USER_ID_HEADER)).toBe(RESEARCHER_ID);
  });

  test.each([
    ["corrected_payload (fechado no BFF)", { answer: "ok", corrected_payload: { hours: 40 } }],
    ["resposta vazia", { answer: "   " }],
    ["resposta acima de 4000", { answer: "a".repeat(4001) }],
  ])("corpo inválido (%s) devolve 400", async (_label, body) => {
    // Act
    const res = await postAnswer(PENDING_OPEN_ID, post(body), deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("CSRF: Origin de outro host devolve 403", async () => {
    // Act
    const res = await postAnswer(PENDING_OPEN_ID, post({ answer: "ok" }, "researcher", { Origin: "http://evil.test" }), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("409 vira STATE_CONFLICT com motivo conhecido e sem o detail do backend", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "detalhe interno", code: "pending_closed", current_status: "draft" }, 409));

    // Act
    const res = await postAnswer(PENDING_OPEN_ID, post({ answer: "ok" }), deps);

    // Assert
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body).toMatchObject({ code: "STATE_CONFLICT", reason: "pending_closed", current_status: "draft" });
    expect(JSON.stringify(body)).not.toContain("detalhe interno");
  });

  test("409 com motivo desconhecido não repassa o código do backend", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "x", code: "<script>", current_status: "hack" }, 409));

    // Act
    const body = await (await postAnswer(PENDING_OPEN_ID, post({ answer: "ok" }), deps)).json();

    // Assert
    expect(body).toMatchObject({ code: "STATE_CONFLICT", reason: null, current_status: null });
  });

  test("403 do backend (papel não designado) vira FORBIDDEN", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "papel sem permissão" }, 403));

    // Act
    const res = await postAnswer(PENDING_OPEN_ID, post({ answer: "ok" }, "manager"), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(await res.json()).toMatchObject({ code: "FORBIDDEN" });
  });
});

describe("BFF: aprovação formal", () => {
  test("gerente aprova com identidade de gerente", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse(approvalOut(), 201));

    // Act
    const res = await postApproval(ARTIFACT_ID, post({ decision: "approve", comment: null }, "manager"), deps);

    // Assert
    expect(res.status).toBe(201);
    expect(sent().url).toBe(`${BACKEND}/api/v1/artifacts/${ARTIFACT_ID}/approval`);
    expect(sent().headers.get(ROLE_HEADER)).toBe("manager");
  });

  test("pesquisador não aprova: 403 sem chamar o backend", async () => {
    // Act
    const res = await postApproval(ARTIFACT_ID, post({ decision: "approve" }, "researcher"), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("sem segredo, a aprovação fica indisponível (503) sem chamar o backend", async () => {
    // Arrange
    env = { ...env, reviewerIdentitySecret: null };

    // Act
    const res = await postApproval(ARTIFACT_ID, post({ decision: "reject" }, "manager"), deps);

    // Assert
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ code: "IDENTITY_UNAVAILABLE" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

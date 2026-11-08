import { beforeEach, describe, expect, test, vi } from "vitest";
import { IDENTITY_SECRET_HEADER, ROLE_HEADER, USER_ID_HEADER, type BffDeps } from "@/lib/server/bff-core";
import type { ServerEnv } from "@/lib/server/env";
import {
  deleteLink,
  getConfig,
  getRun,
  listLinks,
  listPublications,
  postGenerate,
  postLink,
  postPublish,
} from "@/lib/server/integrations-bff";
import { jsonResponse, MANAGER_ID, RESEARCHER_ID } from "@/test/api-fixtures";
import { PROJECT_ID } from "@/test/project-fixtures";

const SECRET = "s".repeat(40);
const BACKEND = "http://backend.test";
const LINK_ID = "7b0f7c64-6a4f-4d57-8f5e-0d6a2f7a9a11";
const ARTIFACT_ID = "9f3c1d2e-0000-4000-8000-000000000001";
const NOW = "2026-11-08T15:00:00Z";

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
let deps: BffDeps;

beforeEach(() => {
  const env: ServerEnv = {
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

const link = (kind = "drive_folder") => ({
  id: LINK_ID,
  project_id: PROJECT_ID,
  kind,
  url: "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
  display_name: "Projetos 2026",
  status: "active",
  last_check_at: NOW,
  created_at: NOW,
});

const publication = (overrides: Record<string, unknown> = {}) => ({
  id: LINK_ID,
  project_id: PROJECT_ID,
  link_id: LINK_ID,
  link_kind: "drive_folder",
  artifact_id: ARTIFACT_ID,
  title: "Relatório BASHO — Quantização — 9f3c1d2e",
  status: "queued",
  attempts: 0,
  external_url: null,
  error_code: null,
  updated_at: NOW,
  ...overrides,
});

function get(role = "manager"): Request {
  return new Request("http://bff.test/api/bff/x", { headers: { "X-Demo-Role": role } });
}

function send(method: string, body: unknown, role = "manager", headers: Record<string, string> = {}): Request {
  return new Request("http://bff.test/api/bff/x", {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { "Content-Type": "application/json", Origin: "http://bff.test", "X-Demo-Role": role, ...headers },
  });
}

function sent(index = 0): { url: string; method: string; headers: Headers; body: unknown } {
  const [url, init] = fetchMock.mock.calls[index] ?? [];
  return {
    url: String(url),
    method: String(init?.method),
    headers: new Headers(init?.headers),
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  };
}

describe("BFF: autorizar link", () => {
  test("gerente autoriza; o BFF injeta a identidade e valida a resposta", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ ...link(), interno: "x" }, 201));

    // Act
    const res = await postLink(PROJECT_ID, send("POST", { url: "https://drive.google.com/drive/folders/abc" }), deps);

    // Assert
    expect(res.status).toBe(201);
    const call = sent();
    expect(call.url).toBe(`${BACKEND}/api/v1/projects/${PROJECT_ID}/links`);
    expect(call.headers.get(ROLE_HEADER)).toBe("manager");
    expect(call.headers.get(USER_ID_HEADER)).toBe(MANAGER_ID);
    expect(call.headers.get(IDENTITY_SECRET_HEADER)).toBe(SECRET);
    expect(JSON.stringify(await res.json())).not.toContain("interno");
  });

  test("pesquisador é barrado no BFF e o backend nem é chamado", async () => {
    // Act
    const res = await postLink(PROJECT_ID, send("POST", { url: "https://drive.google.com/drive/folders/abc" }, "researcher"), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("acesso negado do provedor chega com a orientação do backend", async () => {
    // Arrange
    const detail = "O Basho não consegue acessar este link. Compartilhe a pasta como Editor com basho@x.iam.gserviceaccount.com.";
    fetchMock.mockResolvedValue(jsonResponse({ detail, code: "access_denied" }, 422));

    // Act
    const res = await postLink(PROJECT_ID, send("POST", { url: "https://drive.google.com/drive/folders/abc" }), deps);

    // Assert
    expect(res.status).toBe(422);
    expect(await res.json()).toMatchObject({ code: "LINK_REJECTED", message: detail, reason: "access_denied" });
  });

  test("integração sem credencial no servidor é 503 com código próprio", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Esta integração não está configurada.", code: "not_configured" }, 503));

    // Act
    const res = await postLink(PROJECT_ID, send("POST", { url: "https://www.notion.so/x" }), deps);

    // Assert
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ code: "INTEGRATION_NOT_CONFIGURED" });
  });

  test("provedor fora do ar é 502 repetível", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "O serviço externo não respondeu.", code: "provider_unavailable" }, 502));

    // Act
    const res = await postLink(PROJECT_ID, send("POST", { url: "https://www.notion.so/x" }), deps);

    // Assert
    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({ code: "PROVIDER_UNAVAILABLE", retryable: true });
  });

  test("segredo divergente (401 do backend) vira indisponibilidade, não erro do usuário", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "identidade do revisor ausente ou não confiável" }, 401));

    // Act
    const res = await postLink(PROJECT_ID, send("POST", { url: "https://www.notion.so/x" }), deps);

    // Assert
    expect(res.status).toBe(503);
  });

  test.each([
    ["corpo com campo extra", { url: "https://drive.google.com/x", extra: 1 }],
    ["link curto demais", { url: "abc" }],
    ["sem url", {}],
  ])("recusa %s sem chamar o backend", async (_name, body) => {
    // Act
    const res = await postLink(PROJECT_ID, send("POST", body), deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("recusa requisição de outra origem (CSRF)", async () => {
    // Act
    const res = await postLink(
      PROJECT_ID,
      send("POST", { url: "https://drive.google.com/drive/folders/abc" }, "manager", { Origin: "http://evil.test" }),
      deps,
    );

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("ID de projeto inválido nunca vira caminho do backend", async () => {
    // Act
    const res = await postLink("../admin", send("POST", { url: "https://drive.google.com/drive/folders/abc" }), deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("BFF: revogar, listar e publicar", () => {
  test("gerente revoga com DELETE e pesquisador não", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ ...link(), status: "revoked" }));

    // Act
    const denied = await deleteLink(PROJECT_ID, LINK_ID, send("DELETE", undefined, "researcher"), deps);
    const ok = await deleteLink(PROJECT_ID, LINK_ID, send("DELETE", undefined, "manager"), deps);

    // Assert
    expect(denied.status).toBe(403);
    expect(ok.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sent()).toMatchObject({ method: "DELETE", url: `${BACKEND}/api/v1/projects/${PROJECT_ID}/links/${LINK_ID}` });
  });

  test("qualquer papel lista links e publicações", async () => {
    // Arrange
    fetchMock.mockResolvedValueOnce(jsonResponse([link()])).mockResolvedValueOnce(jsonResponse({ queued: 0, items: [publication()] }));

    // Act
    const links = await listLinks(PROJECT_ID, get("researcher"), deps);
    const pubs = await listPublications(PROJECT_ID, get("researcher"), deps);

    // Assert
    expect(links.status).toBe(200);
    expect(pubs.status).toBe(200);
    expect(sent(0).headers.get(ROLE_HEADER)).toBe("researcher");
  });

  test("publicar agora enfileira e devolve 202 com a lista", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ queued: 1, items: [publication()] }, 202));

    // Act
    const res = await postPublish(PROJECT_ID, send("POST", undefined), deps);

    // Assert
    expect(res.status).toBe(202);
    expect(await res.json()).toMatchObject({ queued: 1 });
    expect(sent()).toMatchObject({ method: "POST", url: `${BACKEND}/api/v1/projects/${PROJECT_ID}/publications` });
  });

  test("resposta fora do contrato é recusada em vez de repassada", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ queued: 1, items: [{ ...publication(), status: "inventado" }] }, 202));

    // Act
    const res = await postPublish(PROJECT_ID, send("POST", undefined), deps);

    // Assert
    expect(res.status).toBe(502);
  });

  test("configuração informa com quem compartilhar a pasta", async () => {
    // Arrange
    fetchMock.mockResolvedValue(
      jsonResponse({ drive: true, notion: false, github: true, google_service_account_email: "basho@x.iam.gserviceaccount.com" }),
    );

    // Act
    const res = await getConfig(get("manager"), deps);

    // Assert
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ google_service_account_email: "basho@x.iam.gserviceaccount.com" });
    expect(sent().url).toBe(`${BACKEND}/api/v1/integrations/config`);
  });

  test("sem papel declarado nada é chamado", async () => {
    // Act
    const res = await listLinks(PROJECT_ID, new Request("http://bff.test/api/bff/x"), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

const RUN_ID = "5540338a-b51e-4853-8adb-78998819fdab";

const run = (overrides: Record<string, unknown> = {}) => ({
  id: RUN_ID,
  project_id: PROJECT_ID,
  task_kind: "research_report",
  prompt_version: "v2",
  status: "queued",
  attempts: 0,
  max_attempts: 3,
  error: null,
  artifact_status: null,
  updated_at: NOW,
  calls: [],
  ...overrides,
});

describe("BFF: gerar relatório com o agente", () => {
  test("gerente pede o relatório do primeiro pesquisador, com período e chave de idempotência do servidor", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse(run(), 202));

    // Act
    const res = await postGenerate(PROJECT_ID, send("POST", { researcher_id: "ignorado", period: "ignorado" }), deps);

    // Assert
    expect(res.status).toBe(202);
    const call = sent();
    expect(call.url).toBe(`${BACKEND}/api/v1/projects/${PROJECT_ID}/agent-runs`);
    expect(call.headers.get(ROLE_HEADER)).toBe("manager");
    expect(call.headers.get("Idempotency-Key")).toMatch(/^ui-[0-9a-f-]{36}-\d+$/);
    expect(call.body).toMatchObject({
      task_kind: "research_report",
      researcher_id: RESEARCHER_ID, // vem da lista do servidor, nunca do navegador
      period: { timezone: "America/Sao_Paulo", periodicity: "monthly" },
    });
    const period = (call.body as { period: { start: string; end: string } }).period;
    expect((Date.parse(period.end) - Date.parse(period.start)) / 86_400_000).toBe(29);
  });

  test("pesquisador pede o próprio relatório", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse(run(), 202));

    // Act
    await postGenerate(PROJECT_ID, send("POST", undefined, "researcher"), deps);

    // Assert
    expect(sent().headers.get(ROLE_HEADER)).toBe("researcher");
    expect(sent().body).toMatchObject({ researcher_id: RESEARCHER_ID });
  });

  test("run já em andamento (200) é aceito como sucesso", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse(run({ status: "running", attempts: 1 }), 200));

    // Act
    const res = await postGenerate(PROJECT_ID, send("POST", undefined), deps);

    // Assert
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ status: "running" });
  });

  test("limite de runs ativos vira 429 com mensagem clara", async () => {
    // Arrange
    fetchMock.mockResolvedValue(jsonResponse({ detail: "limite de runs em andamento atingido" }, 429));

    // Act
    const res = await postGenerate(PROJECT_ID, send("POST", undefined), deps);

    // Assert
    expect(res.status).toBe(429);
    expect(await res.json()).toMatchObject({ code: "TOO_MANY_RUNS", retryable: true });
  });

  test("sem pesquisador na lista do servidor, nada é chamado", async () => {
    // Arrange
    deps = {
      ...deps,
      env: () => ({
        backendUrl: BACKEND,
        reviewerIdentitySecret: SECRET,
        demoReviewers: [{ userId: MANAGER_ID, role: "manager" }],
      }),
    };

    // Act
    const res = await postGenerate(PROJECT_ID, send("POST", undefined), deps);

    // Assert
    expect(res.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("recusa requisição de outra origem", async () => {
    // Act
    const res = await postGenerate(PROJECT_ID, send("POST", undefined, "manager", { "Sec-Fetch-Site": "cross-site" }), deps);

    // Assert
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("acompanha o run e devolve só os campos do contrato", async () => {
    // Arrange
    fetchMock.mockResolvedValue(
      jsonResponse(
        run({
          status: "failed",
          attempts: 3,
          error: { code: "provider_status", message: "Claude respondeu HTTP 529", retryable: true },
          interno: "x",
        }),
      ),
    );

    // Act
    const res = await getRun(RUN_ID, get("manager"), deps);

    // Assert
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ status: "failed", error: { code: "provider_status" } });
    expect(JSON.stringify(body)).not.toContain("interno");
    expect(sent().url).toBe(`${BACKEND}/api/v1/agent-runs/${RUN_ID}`);
  });

  test("ID de run inválido nunca vira caminho", async () => {
    // Act
    const res = await getRun("../etc", get("manager"), deps);

    // Assert
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

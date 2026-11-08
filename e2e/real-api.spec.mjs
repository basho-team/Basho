import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';

test.skip((process.env.BASHO_E2E_MODE ?? 'api') !== 'api', 'Integração real é executada só no modo API.');

const api = process.env.BASHO_API_URL ?? 'http://127.0.0.1:8765';
const host = new URL(api).hostname;
if (!['127.0.0.1', 'localhost', '[::1]'].includes(host)) throw new Error('API de teste deve ser local.');
const periodQuery = (context) => new URLSearchParams(context.period).toString();

async function jsonOk(request, path) {
  const response = await request.get(`${api}${path}`);
  expect(response.status(), `GET ${path}`).toBe(200);
  return response.json();
}

test('API real: contexto sintético, relatórios persistidos e origem no dossiê (somente leitura)', async ({ request }) => {
  const context = await jsonOk(request, '/api/v1/demo/context');
  expect(context.is_synthetic).toBe(true);
  expect(context.people.some((p) => p.role === 'researcher')).toBe(true);
  const query = periodQuery(context);
  const reports = await jsonOk(request, `/api/v1/projects/${context.project_id}/reports?${query}`);
  expect(reports.length, 'O seed do integrador deve fornecer relatórios.').toBeGreaterThan(0);
  const versions = new Set(reports.map((report) => report.version.id));
  const evidence = await jsonOk(request, `/api/v1/projects/${context.project_id}/evidence`);
  const evidenceById = new Map(evidence.map((event) => [event.id, event]));
  const superseded = new Set(evidence.map((event) => event.supersedes).filter(Boolean));
  const itemsById = new Map();
  for (const report of reports) {
    for (const [kind, field] of [['claim', 'claims'], ['experiment', 'experiments'], ['missing', 'missing']]) {
      report.version[`${kind}_ids`].forEach((id, index) => {
        itemsById.set(`${report.version.id}:${kind}:${id}`, report.version.draft[field][index]);
      });
    }
    expect(report.version.draft.project_id).toBe(context.project_id);
    expect(report.content_hash).toMatch(/^[0-9a-f]{64}$/);
    const stored = await jsonOk(request, `/api/v1/reports/${report.version.id}`);
    expect(stored.content_hash).toBe(report.content_hash);
    const history = await jsonOk(request, `/api/v1/reports/${report.version.id}/history`);
    expect(history.some((h) => h.version.id === report.version.id)).toBe(true);
  }
  const consolidated = await jsonOk(request, `/api/v1/projects/${context.project_id}/consolidation?${query}`);
  expect(consolidated.consolidation).not.toBeNull();
  const dossier = await jsonOk(request, `/api/v1/projects/${context.project_id}/dossier?${query}&fiscal_year=${context.fiscal_year}`);
  expect(dossier.scope.project_id).toBe(context.project_id);
  expect(dossier.consolidation_id).toBe(consolidated.consolidation.consolidation_id);
  expect(dossier.items.length).toBeGreaterThan(0);
  let resolvedSources = 0;
  for (const item of dossier.items) {
    expect(versions.has(item.version_id), 'Dossiê deve apontar para versão atual realmente listada.').toBe(true);
    const original = itemsById.get(`${item.version_id}:${item.item_kind}:${item.item_id}`);
    const owner = reports.find((report) => report.version.id === item.version_id);
    expect(item.researcher_id).toBe(owner.version.draft.researcher_id);
    expect(item.researcher_review_id).toBe(owner.status.researcher.state === 'text_approved' ? owner.status.researcher.review_id : null);
    expect(original, 'ID do item deve resolver na versão exata, não apenas ter formato UUID.').toBeDefined();
    const expectedIds = (original.evidence_ids ?? []).filter((id) => {
      const event = evidenceById.get(id);
      return event && event.tenant_id === dossier.scope.tenant_id &&
        event.project_id === context.project_id && !superseded.has(id);
    });
    expect(item.sources.map((source) => source.reference).sort()).toEqual(expectedIds.map((id) => `evidence:${id}`).sort());
    for (const source of item.sources) {
      resolvedSources++;
      expect(source.tenant_id).toBe(dossier.scope.tenant_id);
      expect(source.project_id).toBe(context.project_id);
      const event = evidenceById.get(source.reference.slice('evidence:'.length));
      expect(event).toBeDefined();
      expect(source.revision).toBe(event.content_hash);
      expect(source.locator).toBe(`report:${item.version_id}/${item.item_kind}/${item.item_id}`);
      expect(source.origin).toBe(event.source);
    }
  }
  expect(resolvedSources, 'O seed deve exercitar ao menos uma origem realmente resolvida.').toBeGreaterThan(0);
});

test('API real: escopo vazio não inventa relatórios ou consolidação', async ({ request }) => {
  const context = await jsonOk(request, '/api/v1/demo/context');
  const emptyProject = randomUUID();
  const query = periodQuery(context);
  expect(await jsonOk(request, `/api/v1/projects/${emptyProject}/reports?${query}`)).toEqual([]);
  const result = await jsonOk(request, `/api/v1/projects/${emptyProject}/consolidation?${query}`);
  expect(result).toEqual({ consolidation: null, summary_markdown: null });
  const missing = await request.get(`${api}/api/v1/projects/${emptyProject}/dossier?${query}&fiscal_year=${context.fiscal_year}`);
  expect(missing.status()).toBe(404);
});

test('API real: revisão sem identidade de servidor é rejeitada sem alterar a versão', async ({ request }) => {
  const context = await jsonOk(request, '/api/v1/demo/context');
  const reports = await jsonOk(request, `/api/v1/projects/${context.project_id}/reports?${periodQuery(context)}`);
  const versionId = reports[0].version.id;
  const before = await jsonOk(request, `/api/v1/reports/${versionId}`);
  const rejected = await request.post(`${api}/api/v1/reports/${versionId}/review`, {
    data: { decision: 'text_approved', comment: 'Teste negativo sintético sem identidade.' },
  });
  expect(rejected.status()).toBe(401);
  const after = await jsonOk(request, `/api/v1/reports/${versionId}`);
  expect(after).toEqual(before);
});

test('API real: checks determinísticos não se apresentam como aprovação ou Checker LLM', async ({ request }) => {
  const context = await jsonOk(request, '/api/v1/demo/context');
  expect(context.ai_checker_available).toBe(false);
  const reports = await jsonOk(request, `/api/v1/projects/${context.project_id}/reports?${periodQuery(context)}`);
  const versionId = reports[0].version.id;
  const before = await jsonOk(request, `/api/v1/reports/${versionId}`);
  const response = await request.post(`${api}/api/v1/reports/${versionId}/checks`);
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(['pass', 'fail']).toContain(result.deterministic.verdict);
  expect(Array.isArray(result.deterministic.issues)).toBe(true);
  expect(result.checker_status).toBe('unavailable');
  expect(result.checker_detail).not.toBe('');
  expect(await jsonOk(request, `/api/v1/reports/${versionId}`)).toEqual(before);
});

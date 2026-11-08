import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';

const base = process.env.BASHO_BFF_URL;
test.skip(!base, 'Requer BASHO_BFF_URL explícita de cópia isolada.');
if (base && !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) throw new Error('BFF deve ser local.');

test('conflito de outra aba recarrega a versão apontada pelo backend', async ({ page, request, context }) => {
  const actual = await (await request.get(`${base}/api/bff/demo/context`)).json();
  const researcher = actual.people.find((p) => p.role === 'researcher');
  const cookie = encodeURIComponent(`${researcher.id}:${researcher.role}`);
  const project = randomUUID();
  const headers = { Cookie: `basho_persona=${cookie}` };
  const eventResponse = await request.post(`${base}/api/bff/projects/${project}/evidence`, {
    headers, data: { kind: 'activity_record', title: 'Teste de conflito entre abas', description: 'Evidência sintética de teste de concorrência entre abas.' },
  });
  expect(eventResponse.status()).toBe(201);
  const event = await eventResponse.json();
  const created = await request.post(`${base}/api/bff/reports`, {
    headers, data: {
      project_id: project, researcher_id: researcher.id, period: actual.period,
      summary: 'Relatório sintético de concorrência em um projeto isolado.',
      claims: [{ section: 'method', text: 'Texto original preservado da versão um.', status: 'supported', evidence_ids: [event.id] }],
      formal_hours_event_ids: [], experiments: [], missing: [],
    },
  });
  expect(created.status()).toBe(201);
  const first = await created.json();
  await page.route('**/api/bff/demo/context', (route) => route.fulfill({ json: { ...actual, project_id: project } }));
  await context.addCookies([{ name: 'basho_persona', value: cookie, url: base }]);
  await page.goto(`${base}/pesquisador`);
  await expect(page.getByRole('button', { name: 'Confirmar v1', exact: true })).toBeVisible();
  // Outro cliente cria v2 sem invalidar o cache desta aba.
  const corrected = await request.post(`${base}/api/bff/reports/${first.version.id}/review`, {
    headers, data: {
      decision: 'changes_requested', comment: 'Correção feita por outro cliente sintético.',
      correction: { reason: 'Correção feita por outro cliente sintético.', operations: [{
        kind: 'revise_claim', claim_id: first.version.claim_ids[0],
        text: 'Texto da versão dois criado em outro cliente.', status: 'supported', evidence_ids: [event.id],
      }] },
    },
  });
  expect(corrected.status()).toBe(201);
  const changed = await corrected.json();
  const rejected = page.waitForResponse((r) => r.url().endsWith(`/reports/${first.version.id}/review`));
  await page.getByRole('button', { name: 'Confirmar v1', exact: true }).click();
  expect((await rejected).status()).toBe(409);
  await expect(page.locator('main [role=alert]')).toContainText('409');
  await page.getByRole('button', { name: 'Abrir a versão atual' }).click();
  await expect(page.getByRole('button', { name: 'Confirmar v2', exact: true })).toBeVisible();
  await expect(page.locator('p').filter({ hasText: 'Texto da versão dois criado em outro cliente.' })).toBeVisible();
  const approved = page.waitForResponse((r) => r.url().endsWith(`/reports/${changed.new_version.id}/review`));
  await page.getByRole('button', { name: 'Confirmar v2', exact: true }).click();
  expect((await approved).status()).toBe(201);
});

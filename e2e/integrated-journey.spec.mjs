import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';

const base = process.env.BASHO_BFF_URL;
test.skip(!base, 'Requer BASHO_BFF_URL explícita da entrega real do integrador.');
if (base && !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) throw new Error('UI deve ser local.');

test('jornada por cliques com projeto de teste isolado e persistência real no BFF/backend', async ({ page, request }) => {
  test.setTimeout(90_000);
  const contextResponse = await request.get(`${base}/api/bff/demo/context`);
  expect(contextResponse.status()).toBe(200);
  const actual = await contextResponse.json();
  expect(actual.is_synthetic).toBe(true);
  const project = randomUUID();
  const marker = `Teste de navegador ${project}`;
  // ÚNICA resposta controlada: seleciona escopo exclusivo para não modificar o seed compartilhado.
  // Não há mock de evidências, relatórios, checks, revisões, consolidação ou dossiê.
  const scoped = { ...actual, project_id: project, project_name: marker };
  await page.route('**/api/bff/demo/context', (route) => route.fulfill({ json: scoped }));
  const researcher = actual.people.find((p) => p.role === 'researcher');
  const manager = actual.people.find((p) => p.role === 'manager');
  const fiscal = actual.people.find((p) => p.role === 'fiscal');
  await page.goto(`${base}/pesquisador`);
  await page.getByRole('combobox', { name: /^Atuando como/ }).first().selectOption(researcher.id);
  await expect(page.getByRole('heading', { name: 'Construir relatório do período' })).toBeVisible();

  await page.getByLabel('Título', { exact: true }).fill(marker);
  await page.getByLabel('Descrição', { exact: true }).fill('Atividade sintética criada pela interface para validar a jornada persistida.');
  const registered = page.waitForResponse((r) => r.url().endsWith(`/projects/${project}/evidence`) && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Registrar evidência', exact: true }).click();
  const evidenceResponse = await registered;
  expect(evidenceResponse.status()).toBe(201);
  const evidence = await evidenceResponse.json();
  await expect(page.getByRole('checkbox', { name: new RegExp(marker) })).toBeVisible();
  await page.getByRole('checkbox', { name: new RegExp(marker) }).check();
  await page.getByLabel('Resumo do período').fill(`Relatório sintético persistido por navegação: ${marker}.`);
  await page.getByPlaceholder('Texto da afirmação').fill(`Método sintético documentado ${marker} com 40 horas`);
  const created = page.waitForResponse((r) => r.url().endsWith('/api/bff/reports') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Criar relatório (versão 1)' }).click();
  const createdResponse = await created;
  expect(createdResponse.status()).toBe(201);
  const first = await createdResponse.json();
  const v1 = first.version.id;
  await expect(page.getByRole('heading', { name: 'Relatório — versão atual v1' })).toBeVisible();
  await page.reload();
  await expect(page.locator('p').filter({ hasText: `Método sintético documentado ${marker} com 40 horas` })).toBeVisible();

  const checked = page.waitForResponse((r) => r.url().endsWith(`/reports/${v1}/checks`));
  await page.getByRole('button', { name: 'Rodar verificações' }).click();
  expect((await checked).status()).toBe(200);
  await expect(page.getByText(/Checks determinísticos:/)).toBeVisible();
  const approved = page.waitForResponse((r) => r.url().endsWith(`/reports/${v1}/review`));
  await page.getByRole('button', { name: 'Confirmar v1', exact: true }).click();
  expect((await approved).status()).toBe(201);

  const correction = page.locator('form').filter({ has: page.getByRole('heading', { name: /Corrigir \(gera nova versão/ }) });
  await correction.getByPlaceholder('Novo texto').fill(`Método revisado ${marker}`);
  await correction.getByRole('checkbox', { name: new RegExp(marker) }).check();
  await correction.getByPlaceholder('Motivo da correção (obrigatório)').fill('Precisar o texto com base na evidência sintética registrada.');
  const corrected = page.waitForResponse((r) => r.url().endsWith(`/reports/${v1}/review`));
  await correction.getByRole('button', { name: 'Gerar nova versão' }).click();
  const correctedResponse = await corrected;
  expect(correctedResponse.status()).toBe(201);
  const changed = await correctedResponse.json();
  const v2 = changed.new_version.id;
  await expect(page.getByRole('heading', { name: 'Relatório — versão atual v2' })).toBeVisible();
  const pendingResponse = await page.request.get(`${base}/api/bff/reports/${v2}`);
  expect((await pendingResponse.json()).status.researcher.state).not.toBe('text_approved');
  await expect(page.locator('p').filter({ hasText: `Método revisado ${marker}` })).toBeVisible();
  await expect.soft(page.getByText('Texto da v2 confirmado.', { exact: true })).toHaveCount(0);
  await expect.soft(page.getByText(/Checks determinísticos:/)).toBeHidden();

  // Histórico preservado e ação desatualizada não confirma outra versão.
  await page.getByRole('button', { name: 'v1', exact: true }).click();
  const rejected = page.waitForResponse((r) => r.url().endsWith(`/reports/${v1}/review`));
  await page.getByRole('button', { name: 'Confirmar v1', exact: true }).click();
  expect((await rejected).status()).toBe(409);
  await expect(page.locator('main [role=alert]')).toContainText('409');
  await page.getByRole('button', { name: 'Abrir a versão atual' }).click();
  const approvedV2 = page.waitForResponse((r) => r.url().endsWith(`/reports/${v2}/review`));
  await page.getByRole('button', { name: 'Confirmar v2', exact: true }).click();
  expect((await approvedV2).status()).toBe(201);
  const stored = await page.request.get(`${base}/api/bff/reports/${v2}`);
  expect((await stored.json()).status.researcher.state).toBe('text_approved');
  const rechecked = page.waitForResponse((r) => r.url().endsWith(`/reports/${v2}/checks`));
  await page.getByRole('button', { name: 'Rodar verificações' }).click();
  const checkedV2 = await rechecked;
  expect((await checkedV2.json()).deterministic.verdict).toBe('pass');
  await expect(page.getByText('aprovado', { exact: true })).toBeVisible();

  await page.getByRole('combobox', { name: /^Atuando como/ }).first().selectOption(manager.id);
  await expect(page.getByRole('heading', { name: 'Consolidação gerencial' })).toBeVisible();
  await expect(page.getByText(`Método revisado ${marker}`, { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Aceitar v2', exact: true }).click();
  await expect(page.getByText('Gerente: Texto confirmado', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: /^Atuando como/ }).first().selectOption(fiscal.id);
  await expect(page.getByRole('heading', { name: /Dossiê do período/ })).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: `Método revisado ${marker}` })).toBeVisible();
  const query = new URLSearchParams(actual.period).toString();
  const dossierResponse = await page.request.get(`${base}/api/bff/projects/${project}/dossier?${query}&fiscal_year=${actual.fiscal_year}`);
  expect(dossierResponse.status()).toBe(200);
  const dossier = await dossierResponse.json();
  const item = dossier.items.find((i) => i.item_id === first.version.claim_ids[0]);
  expect(item.version_id).toBe(v2);
  expect(item.sources[0]).toMatchObject({ reference: `evidence:${evidence.id}`, revision: evidence.content_hash, project_id: project });
  const row = page.getByRole('row').filter({ hasText: `Método revisado ${marker}` });
  await row.getByText('Ver origem completa', { exact: true }).click();
  await expect(row.getByText(`evidence:${evidence.id}`, { exact: true })).toBeVisible();
  await expect(row.getByText(evidence.content_hash, { exact: true })).toBeVisible();
  await expect(row.getByText(v2, { exact: true })).toBeVisible();
  await expect(row.getByText(first.version.claim_ids[0], { exact: true })).toBeVisible();
  await expect(row.getByText(/item localizado na versão exata/)).toBeVisible();
  await expect(row.locator('pre')).toContainText('Atividade sintética criada pela interface');
  expect(dossier.researchers[0].gaps).toContain('formal_hours_missing');
});

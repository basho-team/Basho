import { test, expect } from '@playwright/test';

const base = process.env.BASHO_BFF_URL;
test.skip(!base, 'Requer BASHO_BFF_URL explícita da UI integrada.');
if (base && !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) throw new Error('UI deve ser local.');

test('UI integrada: três papéis consultam backend real e cabem na tela', async ({ page, request }) => {
  const response = await request.get(`${base}/api/bff/demo/context`);
  expect(response.status()).toBe(200);
  const context = await response.json();
  expect(context.is_synthetic).toBe(true);
  for (const [role, path, heading, content] of [
    ['researcher', '/pesquisador', 'Pesquisador', /Relatório — versão atual|Construir relatório do período/],
    ['manager', '/gerente', 'Gerente', 'Consolidação gerencial'],
    ['fiscal', '/fiscal', 'Fiscal', /Dossiê do período/],
  ]) {
    await page.goto(`${base}${path}`);
    await page.getByLabel('Atuando como').selectOption(context.people.find((p) => p.role === role).id);
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: content })).toBeVisible();
    await expect(page.getByText('dados sintéticos', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});

test('UI integrada: indisponibilidade não vira mock e retry recupera contexto real', async ({ page }) => {
  const pattern = '**/api/bff/demo/context';
  await page.route(pattern, (route) => route.fulfill({ status: 503, json: { detail: 'Serviço indisponível em teste controlado.' } }));
  await page.goto(`${base}/pesquisador`);
  await expect(page.locator('main [role=alert]')).toContainText('Serviço indisponível em teste controlado.', { timeout: 15_000 });
  await expect(page.getByRole('heading', { name: /Relatório — versão atual/ })).toHaveCount(0);
  await page.unroute(pattern);
  await page.getByRole('button', { name: 'Tentar novamente' }).click();
  await expect(page.getByLabel('Atuando como')).toBeVisible();
  await expect(page.locator('main [role=alert]')).toHaveCount(0);
});

test('UI integrada: cookie malformado não derruba página nem BFF', async ({ page, context }) => {
  await context.addCookies([{ name: 'basho_persona', value: '%', url: base }]);
  await page.goto(`${base}/pesquisador`);
  await expect(page.getByLabel('Atuando como')).toBeVisible();
  await expect(page.getByText(/Escolha no topo uma persona/)).toBeVisible();
  const result = await page.request.get(`${base}/api/bff/demo/context`);
  expect(result.status()).toBe(200);
});

import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASHO_E2E_URL ?? 'http://127.0.0.1:3101';
const mode = process.env.BASHO_E2E_MODE ?? 'api';
// A apresentação compartilhada tem proteção explícita contra escrita por estes testes.
if (process.env.BASHO_BFF_URL && new URL(process.env.BASHO_BFF_URL).port === '3765') {
  throw new Error('A porta 3765 é reservada à apresentação. Use uma cópia com banco isolado.');
}
if (!['api', 'mock'].includes(mode)) throw new Error('BASHO_E2E_MODE deve ser api ou mock.');

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.mjs',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 30_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});

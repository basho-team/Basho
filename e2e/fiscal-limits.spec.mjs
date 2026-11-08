import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';

const base = process.env.BASHO_BFF_URL;
test.skip(!base || process.env.BASHO_FISCAL_LIMITS !== '1', 'Auditoria explícita de limites fiscais conhecidos; apenas banco isolado.');
if (base && !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) throw new Error('BFF deve ser local.');

async function setup(request) {
  const context = await (await request.get(`${base}/api/bff/demo/context`)).json();
  const researcher = context.people.find((p) => p.role === 'researcher');
  const manager = context.people.find((p) => p.role === 'manager');
  const project = randomUUID();
  async function send(method, path, data, person = researcher) {
    return request[method](`${base}/api/bff/${path}`, {
      headers: { Cookie: `basho_persona=${encodeURIComponent(`${person.id}:${person.role}`)}` },
      ...(data === undefined ? {} : { data }),
    });
  }
  async function evidence(body, person = researcher) {
    const response = await send('post', `projects/${project}/evidence`, {
      kind: 'activity_record', title: 'Evidência de auditoria sintética',
      description: 'Registro exclusivo para auditar limitações de rastreabilidade.', ...body,
    }, person);
    expect(response.status()).toBe(201);
    return response.json();
  }
  async function report(event, hours = []) {
    return send('post', 'reports', {
      project_id: project, researcher_id: researcher.id, period: context.period,
      summary: 'Relatório sintético isolado da auditoria técnico-fiscal.',
      claims: [{ section: 'method', text: 'Método sintético documentado pela evidência.', status: 'supported', evidence_ids: [event.id] }],
      formal_hours_event_ids: hours, experiments: [], missing: [],
    });
  }
  async function dossier() {
    const query = new URLSearchParams(context.period).toString();
    const response = await send('get', `projects/${project}/dossier?${query}&fiscal_year=${context.fiscal_year}`);
    expect(response.status()).toBe(200);
    return response.json();
  }
  return { context, researcher, manager, project, send, evidence, report, dossier };
}

test('horas de outra pessoa devem ser rejeitadas ou permanecer com lacuna explícita', async ({ request }, info) => {
  const s = await setup(request);
  const other = s.context.people.find((p) => p.role === 'researcher' && p.id !== s.researcher.id);
  const hours = await s.evidence({ kind: 'formal_hours_declared', hours: 12, researcher_id: other.id }, s.manager);
  const event = await s.evidence({});
  const response = await s.report(event, [hours.id]);
  if (response.status() === 422) return;
  expect(response.status()).toBe(201);
  const d = await s.dossier();
  await info.attach('hours-scope.json', { body: JSON.stringify({ project: s.project, researcher: s.researcher.id, hoursOwner: other.id, hoursId: hours.id, dossierResearcher: d.researchers[0] }, null, 2), contentType: 'application/json' });
  expect(d.researchers[0].formal_hours, 'Horas de outra pessoa não podem ser consideradas pertinentes.').toEqual([]);
  expect(d.researchers[0].gaps.length).toBeGreaterThan(0);
});

test('substituição permanece detectada após mais de 200 eventos', async ({ request }, info) => {
  test.setTimeout(90_000);
  const s = await setup(request);
  const original = await s.evidence({});
  expect((await s.report(original)).status()).toBe(201);
  await s.evidence({ kind: 'user_correction', supersedes: original.id });
  const before = await s.dossier();
  expect(before.items[0].sources).toEqual([]);
  expect(before.items[0].gaps).toContain('evidence_superseded');
  for (let i = 0; i < 201; i++) await s.evidence({ title: `Evento sintético posterior ${i}` });
  const after = await s.dossier();
  await info.attach('supersedes-page.json', { body: JSON.stringify({ project: s.project, original: original.id, before: before.items[0], after: after.items[0] }, null, 2), contentType: 'application/json' });
  expect(after.items[0].sources, 'Paginação não pode restaurar suporte de evidência substituída.').toEqual([]);
  expect(after.items[0].gaps).toContain('evidence_superseded');
});

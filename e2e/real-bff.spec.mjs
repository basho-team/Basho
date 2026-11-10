import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';

const base = process.env.BASHO_BFF_URL;
test.skip(!base, 'Requer BASHO_BFF_URL explícita de uma entrega real do integrador.');
if (base && !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) {
  throw new Error('BFF de teste deve ser local.');
}

// Integração HTTP real. Não equivale a executar a jornada por cliques na interface.
test('BFF real: escrita isolada, revisão exata, conflito e dossiê persistido', async ({ playwright }) => {
  const client = await playwright.request.newContext({ baseURL: base });
  async function call(method, path, data, status = 200) {
    const response = await client[method](`/api/bff/${path}`, data === undefined ? {} : { data });
    expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
    return response.json();
  }
  try {
    const context = await call('get', 'demo/context');
    expect(context.is_synthetic).toBe(true);
    const researcher = context.people.find((p) => p.role === 'researcher');
    expect(researcher).toBeDefined();
    // Cookie documentado da demonstração; nenhum header privilegiado ou segredo no cliente.
    await client.dispose();
    const authenticated = await playwright.request.newContext({
      baseURL: base,
      extraHTTPHeaders: { Cookie: `basho_persona=${encodeURIComponent(`${researcher.id}:${researcher.role}`)}` },
    });
    const send = async (method, path, data, status = 200, person = researcher) => {
      const options = {
        headers: { Cookie: `basho_persona=${encodeURIComponent(`${person.id}:${person.role}`)}` },
        ...(data === undefined ? {} : { data }),
      };
      const response = await authenticated[method](`/api/bff/${path}`, options);
      expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
      return response.json();
    };
    try {
      const project = randomUUID();
      const marker = `E2E sintético ${project}`;
      const evidence = await send('post', `projects/${project}/evidence`, {
        kind: 'activity_record', title: marker,
        description: 'Execução sintética isolada para verificar rastreabilidade e persistência.',
      }, 201);
      const created = await send('post', 'reports', {
        project_id: project, researcher_id: researcher.id, period: context.period,
        summary: `Relatório de integração HTTP ${marker}.`,
        claims: [{ section: 'method', text: marker, status: 'supported', evidence_ids: [evidence.id] }],
        experiments: [], formal_hours_event_ids: [],
        missing: [{ field: 'formal_hours', question: 'Qual registro formal comprova as horas deste período?', ask_role: 'coordenador' }],
      }, 201);
      const v1 = created.version.id;
      const claim = created.version.claim_ids[0];
      expect((await send('post', `reports/${v1}/checks`, {})).checker_status).toBe('unavailable');
      await send('post', `reports/${v1}/review`, { decision: 'text_approved' }, 201);
      const correction = await send('post', `reports/${v1}/review`, {
        decision: 'changes_requested', comment: 'Precisão textual em teste sintético isolado.',
        correction: {
          reason: 'Precisão textual em teste sintético isolado.',
          operations: [{ kind: 'revise_claim', claim_id: claim, text: `${marker} revisado`, status: 'supported', evidence_ids: [evidence.id] }],
        },
      }, 201);
      const v2 = correction.new_version.id;
      const stale = await send('post', `reports/${v1}/review`, { decision: 'text_approved' }, 409);
      expect(stale.current_version_id).toBe(v2);
      const beforeReview = await send('get', `reports/${v2}`);
      expect(beforeReview.version.claim_ids[0]).toBe(claim);
      expect(beforeReview.status.researcher.state).not.toBe('text_approved');
      await send('post', `reports/${v2}/review`, { decision: 'text_approved' }, 201);
      const stored = await send('get', `reports/${v2}`);
      expect(stored.status.researcher.state).toBe('text_approved');
      expect((await send('get', `reports/${v1}`)).version.draft.claims[0].text).toBe(marker);
      expect((await send('get', `reports/${v2}/history`)).map((r) => r.version.id)).toEqual(expect.arrayContaining([v1, v2]));
      const manager = context.people.find((p) => p.role === 'manager');
      const fiscal = context.people.find((p) => p.role === 'fiscal');
      expect(manager).toBeDefined();
      expect(fiscal).toBeDefined();
      await send('post', `reports/${v2}/review`, { decision: 'text_approved' }, 401, fiscal);
      await send('post', `reports/${v2}/review`, { decision: 'text_approved' }, 201, manager);
      const query = new URLSearchParams(context.period).toString();
      const consolidation = await send('get', `projects/${project}/consolidation?${query}`, undefined, 200, manager);
      const dossier = await send('get', `projects/${project}/dossier?${query}&fiscal_year=${context.fiscal_year}`, undefined, 200, fiscal);
      expect(dossier.consolidation_id).toBe(consolidation.consolidation.consolidation_id);
      const item = dossier.items.find((i) => i.item_id === claim);
      expect(item.version_id).toBe(v2);
      expect(item.sources).toEqual(expect.arrayContaining([expect.objectContaining({
        reference: `evidence:${evidence.id}`, revision: evidence.content_hash, project_id: project,
      })]));
      expect(dossier.researchers[0].gaps).toContain('formal_hours_missing');
    } finally { await authenticated.dispose(); }
  } finally { await client.dispose(); }
});

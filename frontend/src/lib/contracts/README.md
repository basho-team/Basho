# Contrato provisório da UI dos três papéis

**Status: PROVISÓRIO, aguardando ratificação do Vitor (dono dos contratos do backend).**

`provisional.ts` traduz a proposta de `CONTRATOS.md` (pacote de transferência de 07/11/2026) em schemas Zod. Isso permite que as telas de Pesquisador, Gerente e Fiscal avancem antes do backend. Os schemas do PR #30 (`PendingItemOut`, `DossierEntryOut`) ainda não cobrem relatórios por período, revisões, consolidação, despesas nem findings.

## Regras
- A UI importa tipos **só** daqui (e, depois, de `src/lib/api/schema.d.ts`). Não declare formatos paralelos em componentes.
- Gates (`can_forward`, `blocking_reasons`), sinalizações e reanálises são calculados pelo **backend**. A UI exibe, não decide.
- Valores monetários são strings decimais. Ausência é `null`, nunca `0`.
- Quando o OpenAPI real existir, rode `npm run gen:api` e troque `NEXT_PUBLIC_DATA_SOURCE` para `api`. O teste `fixtures.test.ts` vira teste de contrato contra o schema real.

## Para ratificar (Vitor)
1. Estados de revisão: `draft | awaiting_researcher | awaiting_manager | available_to_fiscal`. Como mapeiam para `ArtifactStatus` do ledger (`needs_review`, `approved` etc.)?
2. `ReportSummary.approved_by_researcher` e o gate de encaminhamento: quem calcula e com qual regra exata.
3. `Finding.signal` (4 valores) e `FiscalDecision` como registro separado.
4. `PendingRequest` vs. `PendingItemOut` do PR #30: unificar.
5. `Run` (`queued | running | awaiting_input | completed | failed`): é o job da fila (#10)?
6. `ApiError` (`code`, `message`, `correlation_id`, `retryable`) como envelope de erro da API.
7. Rotas reais para as operações de `src/lib/data/source.ts`.

## API real ligada (#12)
`NEXT_PUBLIC_DATA_SOURCE=api` já usa o contrato real de `/api/v1/reports` (#39) via BFF (`src/app/api/bff`):
- tipos gerados em `src/lib/api/schema.d.ts`; validação de runtime em `src/lib/api/reports.ts`;
- tradução para os tipos desta pasta em `src/lib/data/api-adapters.ts` (só formato, sem regra);
- extensões feitas aqui para caber o contrato real: seções `technological_challenge | hypothesis | method | uncertainty`, estados `text_approved` e `superseded`, `justification`/`created_at` anuláveis e `ReportDetail.period_label`.

Ainda sem rota no backend: contexto, lista de relatórios, consolidação, fiscal e pendências (#5). Até lá, essas operações devolvem `NOT_IMPLEMENTED`.

# Contratos compartilhados (issue #20)

Interfaces combinadas na hora 0 para que backend, agente e frontend avancem em paralelo. **Mudar um contrato exige avisar nas issues/PRs afetados.** O código é a fonte da verdade; este documento é o mapa.

| Contrato | Arquivo | Usado por |
| --- | --- | --- |
| Eventos do ledger, estados de artefato | `backend/src/basho/evidence/contracts.py` | #4, #11, #21 |
| Tools e níveis de permissão | `backend/src/basho/agent/tools.py` | #6, #7, #8 |
| Artefato do Maker (registro de atividade) | `backend/src/basho/agent/artifacts.py` | #8, #9, #13 |
| Checker / checks determinísticos | `backend/src/basho/agent/verifier.py` | #9 |
| Schemas HTTP (pendências, correção, aprovação, dossiê) | `backend/src/basho/compliance/api_contracts.py` | #5, #12, #13 |
| Fixtures GitHub sintéticas | `backend/tests/fixtures/github/` | #7, #8, #14 |
| Exemplo de artefato | `backend/tests/fixtures/activity_record_draft.json` | #9, #12, #13 |

## 1. Evidence Ledger (ADR-0003)
- `NewEvidenceEvent` → entrada de `EvidenceService.append`; o serviço calcula `id`, `content_hash` e `created_at`. O `content_hash` é o SHA-256 (hex minúsculo) do JSON canônico (chaves ordenadas, separadores `,`/`:`, UTF-8, sem NaN) do **envelope de conteúdo imutável** — `tenant_id`, `project_id`, `kind`, `source`, `source_ref`, `actor`, `payload`, `supersedes`, `is_synthetic` — e não apenas do payload, para que a adulteração de qualquer desses campos seja detectável. `id` e `created_at` ficam fora do hash.
- **Dados formais** (`FORMAL_HOURS_DECLARED`, `EXPENSE_DECLARED`) só com `source ∈ {user, formal_system}` — o check determinístico rejeita o resto.
- Correção = novo evento `USER_CORRECTION` com `supersedes`; dependentes → `needs_review` (#11).
- Eventos de agente: `actor.type = agent`, `actor.id ∈ {maker, checker}`, `actor.model` obrigatório.

## 2. Tools (ADR-0005)
- `ToolSpec(name, description, level, input_schema, requires_approval)`; registro falha se faltar `level`.
- `FORMAL` nunca é dado ao agente (`AGENT_ALLOWED_LEVELS`).
- Conteúdo externo (corpo de PR, mensagens) volta em `ToolResult.untrusted_data` e é envelopado no prompt como dado (ADR-0006).
- `EXTERNAL` com aprovação → `status = pending_approval` + `approval_id`; o Maker não espera, segue e registra a pendência.

Tools do MVP: `github_list_commits`, `github_get_pull_request`, `ledger_query_events` (read) · `ledger_record_draft`, `pending_item_open` (write_internal) · `github_create_issue` (external).

## 3. Artefato do Maker
`ActivityRecordDraft`: `claims[]` por seção (desafio, hipótese, método, resultado, incerteza), cada um com ≥ 1 `evidence_id`; horas/participantes só como **referência** a eventos formais; lacunas em `missing[]` viram pendências com pergunta objetiva; `eligibility_note` nunca afirma enquadramento.

## 4. Checker (ADR-0004)
1. `DeterministicChecker.check(artifact, evidence)` — schema, citações existem no mesmo tenant, horas/participantes só de eventos formais, sem afirmação de elegibilidade.
2. `Verifier.verify(artifact, evidence)` — LLM independente. Padrão: **Featherless** (API compatível com OpenAI; `FEATHERLESS_BASE_URL`, `FEATHERLESS_API_KEY`, `CHECKER_MODEL` — ver #9). Fallback: outro modelo Claude com contexto limpo.
3. Ambos retornam `VerificationResult(verdict, issues[], unsupported_claims[], checker)`. Códigos de issue sugeridos: `uncited_claim`, `missing_evidence`, `inferred_hours`, `inferred_participant`, `eligibility_assertion`, `prompt_injection`, `contradiction`.

## 5. API HTTP do MVP (prefixo `/api/v1`)

| Método | Rota | Corpo / resposta | Nível |
| --- | --- | --- | --- |
| GET | `/projects/{id}/pending` | `PendingItemOut[]` | leitura |
| POST | `/pending/{id}/confirm` | `ConfirmationIn` | humano |
| POST | `/events/{id}/correct` | `CorrectionIn` | humano |
| POST | `/artifacts/{id}/approval` | `ApprovalIn` | **formal, só humano** |
| GET | `/projects/{id}/dossier` | `DossierEntryOut[]` (inclui `AgentRunMetrics`) | leitura |
| POST | `/projects/{id}/agent-runs` | dispara job do agente → `{run_id}` | humano |

O frontend gera tipos a partir de `/openapi.json` e usa mocks desses schemas até #5 ficar pronta.

## 6. Fixtures
Todas sintéticas (`_synthetic: true`). O PR #42 tem experimento bem descrito; o #43 é experimento **sem justificativa** (caso principal da demo); o #44 contém **prompt injection** (caso de eval).

## 7. Handoff ResearchOps → Basho (ADR-0009, proposta)
O mapa completo está na [ADR-0009](adr/0009-agente-perfis-de-tarefa-e-orquestrador.md#mapa-de-contratos-handoff--basho). Contratos novos previstos para a primeira entrega (relatório do pesquisador): `TaskProfile`/`TaskKind` (`agent/tasks.py`), `ClaimStatus` e `ResearchReportDraft` (`agent/artifacts.py`), `RunStatus`/`AgentRun` (`agent/runs.py`), `ReportingPeriod` e projeção `report_versions` (dados). Os contratos acima continuam válidos; os novos os estendem sem quebrá-los.

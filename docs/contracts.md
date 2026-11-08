# Contratos compartilhados (issue #20)

Interfaces combinadas na hora 0 para que backend, agente e frontend avancem em paralelo. **Mudar um contrato exige avisar nas issues/PRs afetados.** O código é a fonte da verdade; este documento é o mapa.

| Contrato | Arquivo | Usado por |
| --- | --- | --- |
| Eventos do ledger, estados de artefato | `backend/src/basho/evidence/contracts.py` | #4, #11, #21 |
| Tools e níveis de permissão | `backend/src/basho/agent/tools.py` | #6, #7, #8 |
| Artefato do Maker (registro de atividade, relatório do pesquisador) | `backend/src/basho/agent/artifacts.py` | #8, #9, #13, #38 |
| Perfis de tarefa (`TaskKind`, `TaskProfile`, allowlist) | `backend/src/basho/agent/tasks.py` | #8, #10, #38 |
| Execução do agente (`RunStatus`, `AgentRun`) | `backend/src/basho/agent/runs.py` | #10, #25, #38 |
| Prompts versionados por perfil | `backend/src/basho/agent/prompts/<kind>/<versão>.md` | #8, #38 |
| Checker / checks determinísticos | `backend/src/basho/agent/verifier.py` | #9 |
| Schemas HTTP (pendências, correção, aprovação, dossiê) | `backend/src/basho/compliance/api_contracts.py` | #5, #12, #13 |
| Fixtures GitHub sintéticas | `backend/tests/fixtures/github/` | #7, #8, #14 |
| Exemplo de artefato | `backend/tests/fixtures/activity_record_draft.json` | #9, #12, #13 |
| Exemplo de relatório do pesquisador | `backend/tests/fixtures/research_report_draft.json` | #9, #12, #38 |

## 1. Evidence Ledger (ADR-0003)
- `NewEvidenceEvent` → entrada de `EvidenceService.append`; o serviço calcula `id`, `content_hash` e `created_at`. O `content_hash` é o SHA-256 (hex minúsculo) do JSON canônico (chaves ordenadas, separadores `,`/`:`, UTF-8, sem NaN) do **envelope de conteúdo imutável** — `tenant_id`, `project_id`, `kind`, `source`, `source_ref`, `actor`, `payload`, `supersedes`, `is_synthetic` — e não apenas do payload, para que a adulteração de qualquer desses campos seja detectável. `id` e `created_at` ficam fora do hash. O envelope é montado campo a campo e versionado (`HASH_VERSION`, coluna `hash_version`).
- **Dados formais** (`FORMAL_HOURS_DECLARED`, `EXPENSE_DECLARED`) só com `source ∈ {user, formal_system}` — o check determinístico rejeita o resto.
- Correção = novo evento `USER_CORRECTION` com `supersedes`; dependentes → `needs_review` (#11).
- Eventos de agente: `actor.type = agent`, `actor.id ∈ {maker, checker}`, `actor.model` obrigatório. `source = agent` vale se, e somente se, `actor.type = agent`; `source = user` exige `actor.type = user`; dados formais exigem actor user ou system (system só com `formal_system`); `USER_CORRECTION`/`USER_CONFIRMATION` exigem actor e source `user`.

## 2. Tools (ADR-0005)
- `ToolSpec(name, description, level, input_schema, requires_approval)`; registro falha se faltar `level`.
- `FORMAL` nunca é dado ao agente (`AGENT_ALLOWED_LEVELS`).
- Conteúdo externo (corpo de PR, mensagens) volta em `ToolResult.untrusted_data` e é envelopado no prompt como dado (ADR-0006).
- `EXTERNAL` com aprovação → `status = pending_approval` + `approval_id`; o Maker não espera, segue e registra a pendência.

Tools do MVP: `github_list_commits`, `github_get_pull_request`, `ledger_query_events` (read) · `ledger_record_draft`, `pending_item_open` (write_internal) · `github_create_issue` (external).

**Registro** (`agent/registry.py`). `ToolRegistry` revalida cada `ToolSpec` e recusa na inicialização (`ToolRegistrationError`): spec ausente ou sem `level`, nível `formal`, nome duplicado ou nível diferente de `MVP_TOOLS`. `specs_for(profile)` = allowlist ∩ registro ∩ `AGENT_ALLOWED_LEVELS`.

**Policy** (`agent/policy.py`). `ToolPolicy.execute(ToolCallContext(tenant_id, run_id, profile), tool, arguments)` decide em código a cada chamada: tool desconhecida / nível não permitido / fora da allowlist → `denied` (`error` = `unknown_tool | level_not_allowed | not_in_profile`); `external` com `spec.requires_approval` ou com a configuração do tenant (padrão: requer) → `pending_approval` + `approval_id`, **sem executar**; demais executam com timeout. Falha da tool → `error` genérico (`tool_failed | tool_timeout | invalid_result | tool_error`). `untrusted_data` volta envelopado por `envelope_untrusted` (`<untrusted_data tool="...">`, com `<>&` escapados). Implementações simuladas em `agent/simulated_tools.py` (texto externo só em `untrusted_data`; `data` com identificadores; tudo `is_synthetic`).

**Aprovação** (`agent/approvals.py`). Append-only: `tool_approval_requests` (imutável, guarda a entrada proposta) + `tool_approval_decisions` (`UNIQUE(approval_id)`); estado derivado `pending | approved | rejected`. `decide_approval` grava a decisão e o audit; **não executa** a tool (o worker executa depois, #10). Endpoint humano fica para quando houver auth.

**Audit** (módulo `audit`). `NewAuditEntry(tenant_id, event_type, actor_type, actor_id?, run_id?, tool, level?, decision, outcome, reason_code?, input_summary, approval_id?)`; `input_summary` = só chaves de primeiro nível + tamanho em bytes, **nunca valores**. Tabela `audit_log` fora do ledger (registro operacional, não evidência). Migração `0004_tool_audit`: as três tabelas são append-only (trigger), com RLS forçada por `tenant_id` e só `SELECT, INSERT` para `basho_api`/`basho_worker`.

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
O mapa completo está na [ADR-0009](adr/0009-agente-perfis-de-tarefa-e-orquestrador.md#mapa-de-contratos-handoff--basho). Os contratos abaixo estendem os anteriores sem quebrá-los (`ActivityRecordDraft`, `Claim` e demais seguem válidos). Testes em `backend/tests/test_agent_contracts.py`.

**Perfis de tarefa** (`agent/tasks.py`). `TaskProfile(kind, prompt_version, allowed_tools, output_schema)`; perfil não é agente. A allowlist é validada em código contra o registro de tools (`MVP_TOOLS`, trocável via `context={"tool_registry": ...}`) e `AGENT_ALLOWED_LEVELS`: tool desconhecida ou de nível `formal` → `ToolNotAllowedError` (exposto como `ValidationError`). `TaskKind ∈ {research_report, coordination, technical_fiscal, investigation}`, mas só `research_report` tem perfil executável; `get_profile` dos demais → `ProfileNotAvailableError`. `RESEARCH_REPORT_PROFILE` usa as tools `read` + `ledger_record_draft` e `pending_item_open`, **sem `external`**. Prompt em `prompts/research_report/v1.md`, carregado por `load_prompt` (incluído no wheel).

**Relatório do pesquisador** (`agent/artifacts.py`). `ResearchReportDraft(project_id, researcher_id, period, summary, claims[], experiments[], missing[], formal_hours_event_ids[], eligibility_note)`, sem campos numéricos de horas ou valores.
- `ReportingPeriod(start, end, timezone, periodicity)`: datas inclusivas, `end ≥ start`, fuso IANA válido; período **operacional**, distinto do ano-base fiscal.
- `ReportClaim.status` (`ClaimStatus`): `supported` ⇒ ≥ 1 `evidence_id` e sem `dispute_reason`; `pending` ⇒ `question` objetiva + `ask_role`; `disputed` ⇒ `dispute_reason` + evidências em conflito. `supported` é **só pré-condição de schema**: a correspondência real entre texto e evidência é verificada pelos checks determinísticos (#9) e pelo Checker.
- `ExperimentOutcome(description, outcome, evidence_ids)` com `outcome ∈ {positive, negative, inconclusive}`. Pré-condição de schema: toda evidência de um claim `supported` da seção `result` precisa estar coberta por algum `ExperimentOutcome`. Isso não garante sozinho que nenhum resultado negativo foi omitido: a garantia vem do check determinístico (#9), que compara `experiments[]` com os experimentos do período no ledger.
- `ReportClaim` proíbe campos de outro status e `evidence_ids` repetidos; `eligibility_note` é fixa no texto padrão (regra 7).

**Execução** (`agent/runs.py`). `AgentRun(id, tenant_id, task_kind, prompt_version, status, correlation_id, parent_run_id, idempotency_key, attempts, max_attempts, created_at, updated_at, error)`. `RunStatus` é estado de execução, **nunca** de conformidade ou revisão. Transições (`ALLOWED_TRANSITIONS`, `can_transition`): `queued → running | failed`; `running → queued` (retry transitório) `| awaiting_input | completed | failed`; `awaiting_input`, `completed` e `failed` são terminais. A resposta humana a `awaiting_input` cria novo run com o mesmo `correlation_id` e `parent_run_id`. Invariantes: `attempts ≤ max_attempts`; `running` exige `attempts ≥ 1`; `failed` exige `RunError(code, message, retryable)` (sem segredos/PII); `completed` e `awaiting_input` sem `error`; `queued` com `error` só se `retryable` e com tentativas restantes; `updated_at ≥ created_at`. Mudança de estado só por `transition_run` / `fail_or_retry`, que revalidam (`model_copy` do Pydantic não valida); `fail_or_retry` decide por código entre retry e `failed`.

Ainda previstos (dados): projeção `report_versions` e persistência de `agent_runs`.

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
| Persistência e API de relatórios (`report_versions`, `report_reviews`) | `backend/src/basho/reports/{schemas,service,api}.py` | #39, #42, frontend |

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

**Policy** (`agent/policy.py`). `ToolPolicy.execute(ToolCallContext(tenant_id, run_id, profile), tool, arguments)` decide em código a cada chamada: tool desconhecida / nível não permitido / fora da allowlist → `denied` (`error` = `unknown_tool | level_not_allowed | not_in_profile`); `external` com `spec.requires_approval` ou com a configuração do tenant (padrão: requer) → `pending_approval` + `approval_id`, **sem executar**; demais executam com timeout. A policy usa a spec **congelada no registro** (`RegisteredTool`), nunca `tool.spec` lido na hora. Entrada de `external` acima de `MAX_APPROVAL_ARGUMENTS_BYTES` → `denied` (`arguments_too_large`). Falha da tool → `error` genérico (`tool_failed | tool_timeout | invalid_result | tool_error | cancelled`); `error` que não seja código é trocado por `tool_error`, e `data` só leva identificadores (texto livre, inclusive o escrito pelo próprio Maker em rascunhos, volta em `untrusted_data`). Cancelamento também gera audit. `untrusted_data` volta envelopado por `envelope_untrusted` (`<untrusted_data tool="...">`, com `<>&` escapados). Implementações simuladas em `agent/simulated_tools.py` (texto externo só em `untrusted_data`; `data` com identificadores; tudo `is_synthetic`).

**Aprovação** (`agent/approvals.py`). Append-only: `tool_approval_requests` (imutável, guarda a entrada proposta) + `tool_approval_decisions` (`UNIQUE(approval_id)`); estado derivado `pending | approved | rejected`. `decide_approval` grava a decisão e o audit; **não executa** a tool (o worker executa depois, #10). Endpoint humano fica para quando houver auth.

**Audit** (módulo `audit`). `NewAuditEntry(tenant_id, event_type, actor_type, actor_id?, run_id?, tool, level?, decision, outcome, reason_code?, input_summary, approval_id?)`; `input_summary` = só chaves de primeiro nível + tamanho em bytes, **nunca valores**. Tabela `audit_log` fora do ledger (registro operacional, não evidência). Migração `0004_tool_audit`: as três tabelas são append-only (trigger), com RLS forçada por `tenant_id` e só `SELECT, INSERT` para `basho_api`/`basho_worker` — exceto `tool_approval_decisions`, em que o `basho_worker` só tem `SELECT` (o agente não aprova o próprio pedido). CHECKs compostos repetem no banco as invariantes de `NewAuditEntry`. `input_summary.keys` só traz chaves declaradas no `input_schema` da tool.

## 3. Artefato do Maker
`ActivityRecordDraft`: `claims[]` por seção (desafio, hipótese, método, resultado, incerteza), cada um com ≥ 1 `evidence_id`; horas/participantes só como **referência** a eventos formais; lacunas em `missing[]` viram pendências com pergunta objetiva; `eligibility_note` nunca afirma enquadramento.

## 4. Checker (ADR-0004)
Implementado em `basho.agent.checks` e `basho.agent.checker` (#9). Vale para `ActivityRecordDraft` e `ResearchReportDraft` (`VerifiableArtifact`).

1. `ReportDeterministicChecker(tenant_id).check(artifact, evidence)`: roda antes de qualquer LLM, sem banco. Qualquer issue `blocker` ou `major` vira `fail`.
   - `unknown_evidence` (blocker): citação que não está nas evidências do mesmo tenant (inclui outro tenant);
   - `formal_hours_not_formal` (blocker): `formal_hours_event_ids` que não é `FORMAL_HOURS_DECLARED` de origem `user`/`formal_system`;
   - `formal_data_in_text` (major): horas ou valores (`120 horas`, `40h`, `R$`) escritos no texto; `%` e `p.p.` são permitidos;
   - `eligibility_assertion` (blocker): texto afirma elegibilidade ou enquadramento (`eligibility_note` fixa fica de fora);
   - `prompt_injection` (major): evidência citada contém instrução embutida.
2. `Verifier.verify(artifact, evidence)`: LLM independente que recebe **só** o artefato e as evidências citadas, envelopadas como `<evidence untrusted="true">` (`build_checker_input`, sem parâmetro para raciocínio do Maker). Prompt versionado em `agent/prompts/checker/v1.md`.
   - `OpenAICompatibleVerifier`: padrão **Featherless** (`FEATHERLESS_BASE_URL`, `FEATHERLESS_API_KEY`, `CHECKER_MODEL`); trocar de provedor é só config.
   - `ClaudeVerifier`: fallback com contexto limpo (`claude-sonnet-5-5` por padrão).
   - Envelope: `< > &` do conteúdo são escapados (não dá para fechar `<evidence>`); citação ausente vira `<evidence missing="true" />`; payload de `FORMAL_HOURS_DECLARED` não vai ao provedor (LGPD).
   - `ClaudeVerifier` exige `maker_model` e recusa modelo igual ao do Maker.
   - `pass` com issue `blocker`/`major` ou com `unsupported_claims` vira `fail` (`checker_inconsistent_verdict`); resposta truncada vira `fail` (`checker_truncated`).
   - `FallbackVerifier`: sem chave, timeout, erro de rede ou HTTP → fallback. Resposta inválida ou recusa **não** cai no fallback: vira `fail` com `checker_invalid_response`/`checker_refused`.
3. `verify_artifact(...)` → `VerificationOutcome.status`: `draft` (checks falharam; o Maker refaz, máx. 2), `verified` (Checker `pass`) ou `needs_human` (Checker discorda, com as divergências).
4. `verification_event(...)` monta o `VERIFICATION_RESULT` para `EvidenceService.append`: actor `agent`/`checker` com o modelo usado, payload com `status`, `prompt_version` e os dois resultados.
5. Ambos retornam `VerificationResult(verdict, issues[], unsupported_claims[], checker)`. Códigos do Checker LLM: `unsupported_by_evidence`, `negative_result_omitted`, `formal_data_in_text`, `eligibility_assertion`, `prompt_injection`, `contradiction` (mesmo vocabulário dos eval cases de relatórios, PR #43). `negative_result_omitted` fica com o Checker até o ledger ter desfecho estruturado de experimento.

## 5. API HTTP do MVP (prefixo `/api/v1`)

| Método | Rota | Corpo / resposta | Nível |
| --- | --- | --- | --- |
| GET | `/projects/{id}/pending` | `PendingItemOut[]` | leitura |
| POST | `/pending/{id}/confirm` | `ConfirmationIn` | humano |
| POST | `/events/{id}/correct` | `CorrectionIn` | humano |
| POST | `/artifacts/{id}/approval` | `ApprovalIn` | **formal, só humano** |
| GET | `/projects/{id}/dossier` | `DossierEntryOut[]` (inclui `AgentRunMetrics`) | leitura |
| POST | `/projects/{id}/agent-runs` | dispara job do agente → `{run_id}` | humano |
| GET | `/reports/{version_id}` | `ReportVersionOut` (versão + status por papel da versão atual) | leitura |
| POST | `/reports/{version_id}/review` | `ReviewIn` → `ReviewOut` (201); versão que não é a atual → **409** `VersionConflictOut` | **formal, só humano** |

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

**Persistência de relatórios** (#39, sobre o domínio de `basho.reports` do PR #43). Tabelas `reporting_periods`, `report_versions` e `report_reviews` (migração `0003`), append-only (trigger + REVOKE), com `tenant_id` e RLS forçada.
- `report_versions` guarda o `ReportVersion` do domínio: `draft` (JSONB), IDs de item em colunas paralelas (`claim_ids`, `experiment_ids`, `missing_ids`), `change` (`ChangeRecord`, JSONB), `supersedes_id`, `content_hash` (SHA-256 do JSON canônico do draft), `cited_evidence_ids` e `evidence_event_id`.
- Cada versão é também um evento `activity_record` no ledger, com `supersedes` apontando para o evento da versão anterior. Cada revisão gera `user_confirmation` (`text_approved`) ou `user_correction` (`changes_requested`, com `supersedes` para o evento da versão revisada).
- `POST /reports/{id}/review`: o domínio (`review_version`) decide; versão que não é a atual → `VersionConflictError` → 409, sem gravar nada. `correction` (só com `changes_requested`) vira `ReportCorrection` → versão N+1; a versão revisada é preservada e a aprovação dela não vale para a nova.
- Citações são conferidas no ledger (mesmo tenant e projeto); `formal_hours_event_ids` só aceitam `formal_hours_declared`.
- Identidade do revisor (placeholder até #47): headers `X-Basho-User-Id`/`X-Basho-Role` só valem com `X-Basho-Identity-Secret` igual a `REVIEWER_IDENTITY_SECRET` (segredo do BFF, tempo constante); sem segredo configurado → 503. Eventos de revisão gravam `identity_verified: false`.
- Privilégios: `basho_worker` cria versões, mas só **lê** `report_reviews` (revisão é ação formal); `basho_api` lê e insere nas três tabelas.

Ainda previsto (dados): persistência de `agent_runs`.

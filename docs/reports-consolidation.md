# Relatórios de pesquisa e consolidação gerencial (proposta)

> **Status: proposta para ratificação.** Domínio puro em `backend/src/basho/reports/`, sem banco, rotas, LLM ou UI. Apoia-se na ADR-0009 (**proposta**) e no `ResearchReportDraft` de #38/#41, que **não foi alterado**. Persistência e endpoints continuam na #39; consolidação persistida e integração na #42. Os tipos abaixo só viram contrato depois do aceite de Vitor (contratos) e Carlos (agente/dados).

## O que existe
| Módulo | Responsabilidade |
|---|---|
| `reports/versions.py` | `ReportVersion` imutável (`number`, `supersedes_id`, `ChangeRecord`, IDs estáveis de item); `create_first_version`; `validate_history` (cadeia 1..N); `review_version` só sobre a versão atual → `VersionConflictError` (409), papel `researcher` só pelo autor → `ReviewerNotAllowedError`. |
| `reports/corrections.py` | `ReportCorrection(base_version_id, author, reason, operations[])` → versão N+1 revalidada. Operações **por ID**: `revise_claim`, `add_claim`, `withdraw_claim` (com motivo), `revise_experiment_outcome` (evidência + motivo), `add_experiment`, `resolve_missing`. |
| `reports/consolidation.py` | `consolidate([ReportInput])` → `ManagerConsolidation` com envelope (ID, tenant, projeto, período, entradas), estado de revisão por papel, avanços, resultados (todos os desfechos), incertezas, perguntas abertas, conflitos e contagem por desfecho; cada item com `SourceRef`. |

## Decisão 1 — IDs estáveis de item (corrige referência por posição)
**Problema (v. `aabfaaf`):** itens eram referenciados por posição (`claims[2]`). `withdraw_claim` deslocava posições, e `ChangeRecord.affected_claims` guardava índices da versão-base, ambíguos na nova.

**Decisão (compatível com `ResearchReportDraft`, sem campo novo nele):**
- `ReportVersion` carrega `claim_ids`, `experiment_ids`, `missing_ids`, **paralelos** a `draft.claims/experiments/missing` (mesmo tamanho, sem repetição; validado).
- **Geração:** `uuid5(REPORT_ITEM_NAMESPACE, "<versão de origem>/<tipo>/<ordem>")`. Versão de origem = a que introduziu o item; ordem = posição entre os itens daquele tipo introduzidos nela. Na v1 (`create_first_version`) a ordem é a posição no draft; em correções, a ordem do `add_*` na correção. Mesma entrada ⇒ mesmo ID.
- **Preservação:** `revise_*` mantém o ID; `withdraw_claim` remove o ID só da versão nova; `resolve_missing` remove a lacuna só da versão nova. Versões antigas são imutáveis e mantêm seus IDs; o mesmo ID em versões diferentes é o mesmo item lógico.
- **Consolidação nunca cria IDs de item:** só lê os da versão.
- `ChangeRecord` registra por ID: `affected_claim_ids`, `added_claim_ids`, `withdrawn[{claim_id, reason}]`, `affected_experiment_ids`, `added_experiment_ids`, `resolved_gaps`.

## Decisão 2 — Lacuna resolvida estruturada (corrige registro só em texto)
`ChangeRecord.resolved_gaps[] = ResolvedGap(missing_id, field, evidence_ids, formal_hours_event_ids)`. O texto em `operations[]` virou só resumo legível. `formal_hours` continua exigindo `formal_hours_event_ids`.

## Decisão 3 — Revisão por papel (corrige gerente apagando pesquisador)
- `ReportReview.reviewer_role: ReviewerRole ∈ {researcher, manager}` (antes `str`).
- `ReportStatus.researcher` e `ReportStatus.manager` são `RoleReview(state, review_id)` independentes: cada um é a revisão mais recente **daquele papel** sobre a versão atual.
- `approved_version_number`, `approval_outdated` e `all_text_approved` consideram só o **pesquisador**: aprovação do gerente não marca o texto como aprovado pelo autor.
- Papel `researcher` só pode ser usado pelo `researcher_id` do relatório.

## Decisão 4 — Origem, contexto e identificação da consolidação (sem duplicar)
- `SourceRef(researcher_id, version_id, version_number, item_kind, item_id, researcher_review_id)`: `(version_id, item_kind, item_id)` resolve o item exato; `researcher_review_id` é a revisão que aprovou o texto **daquela** versão (ou `None`), substituindo o booleano `text_approved`.
- Tenant, projeto e período (completo: início, fim, fuso, periodicidade) ficam **só no envelope** `ManagerConsolidation` (`tenant_id`, `project_id`, `period`), como sugerido pelo Codex; não se repetem por item.
- `consolidation_id` = `uuid5` de tenant + IDs das versões de entrada + IDs das revisões consideradas (ordenados). Mesmas entradas ⇒ mesmo ID; nova versão ou nova revisão ⇒ novo ID. `input_version_ids` e `input_review_ids` permitem reproduzir a consolidação.
- `OpenQuestion` de claim `pending` traz também `text` e `evidence_ids` parciais (sugestão do Codex).

## Invariantes garantidas por código (com teste)
- Versão anterior nunca muda; correção ou revisão sobre versão antiga → conflito.
- Aprovação da v1 não vale para a v2 (`approval_outdated`).
- `text_approved` é aprovação do **texto**; **não é aprovação fiscal** (`CONSOLIDATION_NOTE`).
- Nenhuma operação remove experimento; mudar desfecho exige evidência e motivo.
- Afirmação só vira `supported` com evidência citada.
- Consolidação não soma horas; rejeita tenant/projeto/período distintos, pesquisador duplicado e revisão órfã.
- Regressões dos três defeitos em `tests/test_reports_regressions.py`.

## Dependências (não implementadas aqui)
- **Hash de conteúdo da `ReportVersion`** → #39. O ledger já tem `content_hash` para `EvidenceEvent` (#40, ADR-0003), mas o hash de versão de relatório precisa da persistência/serialização canônica de `report_versions`, ainda inexistente.
- **Evidência citada já substituída** (`supersedes`) → #11 (e consulta ao ledger). O domínio não acessa o ledger.
- Conferir no ledger que `formal_hours_event_ids` são `FORMAL_HOURS_DECLARED` e que `evidence_ids` existem no mesmo tenant/projeto → #9/#39.

## Perguntas para ratificar
**Vitor (contratos/persistência, #39/#42):**
1. Persistir os IDs de item como colunas paralelas/JSON em `report_versions` ou como tabela `report_items(version_id, item_kind, item_id, position)`? O algoritmo de geração (Decisão 1) é aceitável?
2. `ChangeRecord` fica em `report_versions` ou vira `EvidenceEvent` com `supersedes` (ADR-0003)?
3. Vocabulário `ReviewerRole`/`ReviewDecision`/`ReviewState` × estados do handoff (`awaiting_researcher | awaiting_manager | available_to_fiscal`) × `ArtifactStatus`.
4. Rota (`GET /api/v1/projects/{id}/consolidation?period=`) e formato de `ManagerConsolidation` para o OpenAPI; a consolidação é calculada na leitura ou persistida pelo `consolidation_id`?

**Carlos (agente/dados):**
5. Onde verificar que horas citadas são `FORMAL_HOURS_DECLARED` (#9 ou service de `reports`)?
6. Correção humana dispara novo run de `research_report` (Maker + Checker) antes de voltar à revisão? O Maker precisa receber os IDs de item para preservar a identidade?

**Codex (técnico-fiscal):** `SourceRef` + envelope cobrem os pontos (1), (2) e a sugestão de `OpenQuestion`; (3)–(5) da sua revisão dependem de #39/#11 e do resolvedor de evidências.

## Limitações conhecidas
- Sem persistência, RLS real ou endpoints; `tenant_id` só é conferido entre as entradas.
- `consolidation_id` identifica o conjunto de entradas, não um registro persistido; não há `generated_at` (para manter o cálculo determinístico).
- IDs de item de versões criadas fora de `create_first_version`/`apply_correction` (ex.: saída direta do Maker para uma v2) precisam ser fornecidos pelo chamador; o Maker ainda não conhece IDs (pergunta 6).
- Não detecta números de horas no texto (#9) nem verifica se a evidência sustenta o texto (Checker).
- Propagação de `needs_review` a dependentes fora do relatório depende de #11.

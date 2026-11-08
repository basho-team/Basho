# Relatórios de pesquisa e consolidação gerencial (proposta)

> **Status: proposta para ratificação.** Domínio puro em `backend/src/basho/reports/`, sem banco, rotas, LLM ou UI. Apoia-se na ADR-0009 (**proposta**) e no `ResearchReportDraft` de #38/#41, que **não foi alterado**. Persistência e endpoints continuam na #39. Os tipos abaixo só viram contrato depois do aceite de Vitor (contratos) e Carlos (agente/dados).

## O que existe
| Módulo | Responsabilidade |
|---|---|
| `reports/versions.py` | `ReportVersion` imutável (`number`, `supersedes_id`, `ChangeRecord`); `ReportKey` = projeto + pesquisador + período; `validate_history` (cadeia 1..N); `review_version` só sobre a versão atual → `VersionConflictError` (semântica 409). |
| `reports/corrections.py` | `ReportCorrection(base_version_id, author, reason, operations[])` → versão N+1 revalidada por `ResearchReportDraft`. Operações: `revise_claim`, `add_claim`, `withdraw_claim` (com motivo), `revise_experiment_outcome` (exige evidência + motivo), `add_experiment`, `resolve_missing`. |
| `reports/consolidation.py` | `consolidate([ReportInput])` → `ManagerConsolidation` com status de revisão por pesquisador, avanços, resultados (todos os desfechos), afirmações de resultado, incertezas, perguntas abertas, conflitos e contagem por desfecho. Cada item traz `SourceRef` (pesquisador, versão, item, se o texto foi aprovado). |

## Invariantes garantidas por código (com teste)
- Versão anterior nunca muda; correção sobre versão antiga → conflito.
- Revisão referencia a **versão exata**; aprovação da v1 **não** vale para a v2 (`approval_outdated`).
- `text_approved` = aprovação do **texto** pelo pesquisador; **não é aprovação fiscal** nem enquadramento. A consolidação carrega a nota fixa `CONSOLIDATION_NOTE`.
- Nenhuma operação remove experimento; mudar desfecho negativo/inconclusivo exige evidência e motivo, registrados no `ChangeRecord`.
- Afirmação só vira `supported` com evidência citada (schema `ReportClaim`).
- Lacuna `formal_hours` só fecha com `formal_hours_event_ids`; consolidação **não soma horas**, só lista referências por pesquisador.
- Consolidação rejeita relatórios de projeto/período/tenant distintos, pesquisador duplicado e revisão órfã.

## Perguntas para ratificar
**Vitor (contratos/persistência, #39):**
1. `ReportVersion`/`ReportReview` servem de base para `report_versions`/`report_reviews`? Ou o `ChangeRecord` deve ser um `EvidenceEvent` com `supersedes` (ADR-0003)?
2. `ReviewDecision` (`text_approved | changes_requested`) × estados do handoff (`awaiting_researcher | awaiting_manager | available_to_fiscal`) × `ArtifactStatus`: qual vocabulário fica?
3. Rota de consolidação (`GET /api/v1/projects/{id}/consolidation?period=`) e o formato de `ManagerConsolidation` para gerar os tipos do frontend (PR #35 usa um provisório).

**Carlos (agente/dados):**
4. A `ResolveMissing` precisa confirmar no ledger que os IDs são `FORMAL_HOURS_DECLARED`. Isso fica nos checks determinísticos (#9) ou num service de `reports`?
5. A correção humana deve disparar novo run do perfil `research_report` (Maker + Checker) antes de voltar para revisão?

**Codex/frente técnico-fiscal:** `SourceRef` (versão + item + `text_approved`) é o que a análise fiscal precisa para citar relatórios revisados?

## Limitações conhecidas
- Sem persistência, sem tenant/RLS real (o `tenant_id` só é conferido no histórico), sem endpoints.
- Não verifica se o texto de uma afirmação corrigida contém números de horas (é papel dos checks determinísticos de #9).
- Não verifica se a evidência sustenta o texto (Checker).
- Revisões de gerente e pesquisador usam o mesmo `ReportReview`; o estado considera só a revisão mais recente da versão atual.
- Propagação de `needs_review` a dependentes fora do relatório (findings, pacote) depende de #11.

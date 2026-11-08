# ADR-0009: Agente por perfis de tarefa com orquestrador determinístico

- **Status:** proposta
- **Data:** 2026-11-07
- **Decisores:** Carlos (responsável por agente + dados) — aceite da equipe pendente
- **Relação:** apoia-se na ADR-0008 (proposta, [PR #33](https://github.com/basho-team/Basho/pull/33)); preserva ADR-0002, 0003, 0004, 0005 e 0006

## Contexto e problema
O pacote de handoff ResearchOps ([`docs/handoff/`](../handoff/LEIA_PRIMEIRO.md)) reposiciona o produto em torno de três papéis — pesquisador, gerente e fiscal — e propõe quatro responsabilidades lógicas de agente (documentação de pesquisa, coordenação, análise técnico-fiscal e investigação de pendências), LangGraph para pausa/retomada e contratos mínimos (`EvidenceVersion`, `ReportVersion`, `Review`, `Finding`, `Exception`, `Action/Run`, `Release`). Isso conflita com a ADR-0002 (stack sem LangGraph) e com a regra da ADR-0004 de não criar agentes sem justificativa. A equipe também redistribuiu a frente: Carlos assume agente e dados.

## Opções consideradas
1. Adotar o handoff integralmente, com LangGraph e quatro agentes.
2. Manter só Maker–Checker e GitHub (ADR-0004/0007 originais), ignorando os três papéis.
3. Orquestrador determinístico próprio sobre a fila em Postgres, com as quatro responsabilidades como **perfis de tarefa** do Maker, preservando o Checker independente.

## Decisão
Opção 3.

- **Orquestrador determinístico** no processo worker (ADR-0001/0002): fila em Postgres (`FOR UPDATE SKIP LOCKED`), sem LangGraph. Estado de execução `queued | running | awaiting_input | completed | failed` fica em `agent_runs` e é **separado** do estado de negócio (revisão, sustentação da afirmação, finding). Cada campo tem uma única autoridade. Pausar à espera de um humano encerra o job; a resposta cria um novo job correlacionado, sem request HTTP ou chamada de modelo abertos.
- **Perfis de tarefa**, não agentes: `TaskProfile(kind, prompt_version, allowed_tools, output_schema)` com `kind ∈ {research_report, coordination, technical_fiscal, investigation}`. Cada perfil tem prompt versionado em `backend/src/basho/agent/prompts/<kind>/`, allowlist de tools aplicada pela policy (ADR-0005) e saída estruturada validada por Pydantic. Não há conversa livre entre perfis; o orquestrador encadeia tarefas tipadas. É a leitura literal da ADR-0004 ("especializações são tools e prompts por tarefa").
- **Maker–Checker mantido** (ADR-0004): checks determinísticos antes de qualquer LLM e Checker de outro provedor, que vê só o artefato e as evidências citadas, em artefatos formais.
- **Afirmações** têm status `supported | pending | disputed`. `supported` exige ≥ 1 evidência citada **e** correspondência verificada pelo Checker; `pending` traz a pergunta objetiva ao responsável; `disputed` registra o conflito. Resultado negativo de experimento é preservado, nunca omitido.
- **Fronteira IA/código** (handoff, `ARQUITETURA.md`): a IA interpreta, relaciona, redige e propõe; o código faz somas decimais, deduplicação, transições de estado, autorização, idempotência e gates de liberação. Nenhum gate depende da confiança declarada pelo modelo.
- **Primeira entrega:** só o perfil `research_report` (relatório individual do pesquisador por período). Os demais ficam declarados, sem execução, até terem issue própria.

### Mapa de contratos handoff → Basho

| Handoff | Basho |
|---|---|
| `EvidenceVersion` | `EvidenceEvent` (ledger, ADR-0003); nova versão = evento com `supersedes` |
| `ReportingPeriod` | novo: início/fim, fuso, periodicidade; distinto do ano-base fiscal |
| `ReportVersion` (individual) | novo `ResearchReportDraft` + projeção `report_versions` |
| `Activity/Claim` | `Claim` com `ClaimStatus` |
| `Review` | revisão sobre **versão exata**; versão antiga → conflito (409) |
| `Exception` | `PendingItem` existente (`compliance/api_contracts.py`) |
| `Action/Run` | `AgentRun` (correlação, tentativas, chave de idempotência) |
| `Finding`, `Expense/Allocation`, `Release` | fora desta etapa; entram com o perfil `technical_fiscal` |

## Consequências
- **Positivas:** aproveita os contratos já mergeados (#30) e a stack aceita; os três papéis e as quatro responsabilidades cabem sem novos serviços nem nova dependência; o Checker continua independente.
- **Negativas / custos:** pausa/retomada é código nosso e precisa de testes de reinício e de efeitos externos repetidos; diverge da recomendação de LangGraph do handoff, e Vitor/Thiago precisam estar de acordo.
- **Regras derivadas:**
  - Novo perfil de tarefa exige prompt versionado, allowlist de tools e schema de saída, com teste. Novo *agente* com contexto ou processo próprio continua exigindo ADR.
  - Estado de execução nunca é usado como estado de conformidade ou de revisão.
  - Revisão humana referencia a versão exata do relatório; alteração material depois dela gera nova versão e devolve os dependentes a `needs_review`.
  - Ao ser aceita, atualizar `CLAUDE.md` (regra 4) e `docs/architecture.md` §6.

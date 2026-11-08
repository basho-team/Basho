# Arquitetura do Basho

> Documento vivo. Toda mudança estrutural exige uma ADR em [`docs/adr/`](adr/). Em caso de conflito, **a ADR mais recente aceita prevalece** sobre este texto, e este texto deve ser atualizado.

## 1. Visão

Basho é uma plataforma de IA que **executa e organiza o trabalho operacional de projetos de P&D tecnológico** e, no mesmo fluxo, **constrói continuamente as evidências exigidas pela Lei do Bem** (Lei nº 11.196/2005). Público: PMEs que realizam P&D e usufruem ou pretendem usufruir dos incentivos, observados os requisitos legais.

Princípios inegociáveis:

1. **O sistema executa, o humano supervisiona.** Tarefas operacionais são automatizadas; atos formais/fiscais exigem aprovação humana ([ADR-0005](adr/0005-gates-de-permissao-e-aprovacao-humana.md)).
2. **Nada é inventado.** Horas, valores, alocações, participantes e elegibilidade nunca são inferidos — só vêm de registros formais confirmados por responsáveis.
3. **Tudo é rastreável.** Toda afirmação em um artefato aponta para uma evidência com proveniência ([ADR-0003](adr/0003-evidence-ledger-append-only.md)).
4. **Quem gera não valida.** Artefatos formais passam por um verificador independente, de outro modelo ([ADR-0004](adr/0004-maker-checker-multi-modelo.md)).
5. **Correção propaga.** Corrigir um dado reabre tudo que dependia dele.
6. **O sistema não garante benefício fiscal** nem substitui responsáveis técnicos, contábeis ou legais.

## 2. Contexto (C4 nível 1)

```mermaid
flowchart LR
    pesq[Pesquisadores / Engenheiros]
    gestor[Gestor de P&D]
    fiscal[Contábil / Fiscal]
    basho((Basho))
    gh[(GitHub)]
    llmA[[Anthropic API<br/>Maker]]
    llmB[[Outro provedor LLM<br/>Checker]]

    pesq -- confirma / corrige registros --> basho
    gestor -- acompanha pendências, aprova --> basho
    fiscal -- revisa dossiê, aprova dispêndios --> basho
    basho -- lê commits, PRs, issues --> gh
    basho -- cria issues/comentários autorizados --> gh
    basho --> llmA
    basho --> llmB
```

## 3. Containers (C4 nível 2)

```mermaid
flowchart TB
    subgraph Browser
      web[Next.js App Router<br/>TypeScript + shadcn/ui + TanStack Query]
    end
    subgraph Backend [FastAPI — monólito modular]
      api[API HTTP<br/>Pydantic v2]
      worker[Worker de jobs do agente<br/>fila em Postgres]
    end
    db[(PostgreSQL 16<br/>RLS por tenant)]
    web -- REST/JSON --> api
    api --> db
    worker --> db
    worker -- tools --> gh[(GitHub API)]
    worker --> maker[[Claude — Maker]]
    worker --> checker[[Checker — outro modelo]]
```

- **web**: UI de pendências, correção/aprovação, dossiê. Não contém regra de negócio.
- **api**: endpoints REST, validação de borda, autorização, leitura de projeções.
- **worker**: executa jobs do agente (investigação, rascunho, verificação). Mesmo código do backend, processo separado.
- **db**: única fonte de verdade. Ledger append-only + tabelas de projeção.

## 4. Módulos do backend (C4 nível 3)

Monólito modular ([ADR-0001](adr/0001-monolito-modular.md)). Cada módulo é um pacote em `backend/src/basho/<modulo>/` com `domain/` (entidades, regras puras), `service.py` (casos de uso), `repository.py` (acesso a dados), `api.py` (rotas). **Módulos só se comunicam via `service` público**, nunca importando o repositório de outro módulo.

| Módulo | Responsabilidade |
| --- | --- |
| `projects` | Projetos, marcos, desafios tecnológicos, hipóteses |
| `activities` | Atividades/experimentos de P&D e registros de atividade |
| `evidence` | Evidence Ledger: eventos, proveniência, vínculos, hash |
| `people` | Participantes e papéis (dados pessoais minimizados — LGPD) |
| `expenses` | Dispêndios **informados por sistemas/responsáveis**, vinculados a atividades |
| `compliance` | Checagens de completude, lacunas, dossiê, preparação (não decisão) de enquadramento |
| `agent` | Orquestração Maker–Checker, tools, policy de permissões, jobs |
| `connectors` | Adaptadores de fontes externas (GitHub no MVP) |
| `audit` | Log de auditoria imutável de toda ação de agente e humano |

## 5. Evidence Ledger e estados

```mermaid
stateDiagram-v2
    [*] --> draft: Maker rascunha
    draft --> proposed: checks determinísticos OK
    proposed --> verified: Checker aprova
    proposed --> needs_human: Checker discorda
    verified --> approved: humano aprova
    verified --> rejected: humano rejeita
    needs_human --> draft: humano corrige
    approved --> needs_review: evidência dependente corrigida
    needs_review --> draft
```

- `evidence_events` é **append-only** (sem UPDATE/DELETE; reforçado por permissão de banco). Cada evento: `id`, `tenant_id`, `kind`, `source` (github, user, system…), `source_ref` (sha, PR#, doc id), `actor` (usuário ou agente+modelo), `payload` (JSONB), `content_hash` (SHA-256), `created_at`, `supersedes` (opcional).
- Vínculos: `Projeto → Atividade → Evidência ↔ Pessoa ↔ Dispêndio` (tabelas de link com `evidence_event_id`).
- **Correção = novo evento** que `supersedes` o anterior. Um job recalcula dependências e move artefatos afetados para `needs_review`.

## 6. Agente: Maker–Checker

```mermaid
sequenceDiagram
    participant W as Worker
    participant M as Maker (Claude)
    participant D as Checks determinísticos
    participant C as Checker (outro modelo)
    participant H as Humano
    W->>M: tarefa + contexto + tools (policy)
    M-->>W: artefato com citações de evidência
    W->>D: schema, citações existem, sem dados formais inferidos
    alt falha
      D-->>M: erros → nova tentativa (máx. 2)
    end
    W->>C: apenas artefato + evidências citadas
    C-->>W: verdict, issues[], unsupported_claims[]
    alt verified
      W->>H: pronto para aprovação
    else discordância
      W->>H: needs_human com divergências
    end
```

Detalhes em [ADR-0004](adr/0004-maker-checker-multi-modelo.md). Permissões de tools em [ADR-0005](adr/0005-gates-de-permissao-e-aprovacao-humana.md).

## 7. Segurança

Resumo de [ADR-0006](adr/0006-seguranca-rls-lgpd-prompt-injection.md): RLS por `tenant_id`, menor privilégio no banco, LGPD (minimização e separação de dados pessoais), conteúdo externo tratado como **dado, nunca instrução**, audit log imutável, segredos só por variável de ambiente, validação em todas as bordas.

## 8. Desempenho e custo

- Prompt caching nas instruções fixas e definições de tools.
- Roteamento de modelos: modelos menores para triagem/classificação; modelo maior só para redação formal.
- Checker só em artefatos formais.
- Jobs assíncronos em fila Postgres (`SELECT … FOR UPDATE SKIP LOCKED`); sem Redis/Temporal até haver necessidade medida.
- Consultas paginadas e indexadas por `(tenant_id, project_id, created_at)`.

## 9. Estrutura do repositório (alvo)

```
backend/            FastAPI (uv, ruff, mypy, pytest)
  src/basho/<modulo>/
  migrations/       Alembic
  tests/
frontend/           Next.js (App Router, TS strict)
docs/
  architecture.md
  engineering-practices.md
  adr/
docker-compose.yml  Postgres local
.env.example
```

## 10. Recorte do MVP

Ver [ADR-0007](adr/0007-recorte-mvp-hackathon.md).

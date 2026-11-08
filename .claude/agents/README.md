# Subagentes de desenvolvimento do Basho

Subagentes do Claude Code especializados por área. Eles **constroem** o Basho; não são os agentes do produto (Maker/Checker), então não entram no limite da ADR-0004.

Cada agente lê as regras do projeto (`CLAUDE.md`, ADRs, `docs/contracts.md`) antes de agir e traz boas práticas pesquisadas, com fontes.

| Agente | Área | Issues |
|--------|------|--------|
| `basho-ledger` | Evidence Ledger, projetos/atividades/pendências, Alembic, propagação de correções | #4, #5, #11 |
| `basho-agent` | Tools + policy + audit, Maker, checks determinísticos + Checker, fila/worker, confiabilidade | #6, #8, #9, #10, #25 |
| `basho-connectors` | Conector GitHub, seed sintético e repo de demo | #7, #14 |
| `basho-security` | RLS, roles de banco, imutabilidade, LGPD, prompt injection; revisor de PRs sensíveis | #21 + revisões |
| `basho-frontend` | UI de pendências/correção, dossiê, telas de custo/tracing | #12, #13, #23 (UI) |
| `basho-qa` | Integração e2e e evals do Maker/Checker | #22, #24 |
| `basho-infra` | CI, docker-compose, deploy, observabilidade | #26, #23 (backend) |

## Uso

No Claude Code, dentro do repositório:

```
/agents                                   # lista os agentes disponíveis
Use o basho-ledger para implementar a issue #4
Peça ao basho-security para revisar o PR #42
```

## Manutenção

- Mudou uma ADR ou contrato? Atualize os agentes que citam essa regra no mesmo PR.
- Boas práticas novas entram com link da fonte e só se não contrariarem uma ADR. Se contrariarem, proponha uma nova ADR antes.

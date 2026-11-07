# ADR-0003: Evidence Ledger append-only

- **Status:** aceita
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
A comprovação da Lei do Bem depende de rastreabilidade entre atividades, evidências técnicas, pessoas e dispêndios. Correções de usuários precisam refletir em todos os documentos afetados — um botão de "não está correto" que não muda nada é inaceitável.

## Opções consideradas
1. CRUD tradicional com sobrescrita
2. Event sourcing completo
3. **Ledger append-only de evidências + tabelas de projeção**

## Decisão
Opção 3. Tabela `evidence_events` imutável com: `id`, `tenant_id`, `kind`, `source`, `source_ref`, `actor` (usuário ou agente + modelo), `payload` JSONB, `content_hash` SHA-256, `supersedes`, `is_synthetic`, `created_at`. Entidades de domínio (atividades, registros de atividade, dossiê) são projeções que referenciam eventos.

Estados de artefatos formais: `draft → proposed → verified → approved | rejected`, com `needs_human` e `needs_review` (ver `docs/architecture.md` §5).

## Consequências
- **Positivas:** auditabilidade, histórico completo, correções propagáveis, prova de integridade por hash.
- **Negativas:** mais tabelas e um job de recomputação de dependências.
- **Regras derivadas:**
  - Proibido `UPDATE`/`DELETE` em `evidence_events` (garantido por permissão do role do banco e por teste).
  - Toda afirmação de um artefato formal cita ≥ 1 `evidence_event_id`.
  - Correção = novo evento com `supersedes`; artefatos dependentes vão para `needs_review`.
  - Todo evento registra `actor`; eventos de agente registram o modelo usado.

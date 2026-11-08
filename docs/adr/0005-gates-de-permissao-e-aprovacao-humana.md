# ADR-0005: Gates de permissão por tool e aprovação humana

- **Status:** aceita
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
O sistema deve executar trabalho real, mas declarações fiscais, enquadramentos, valores e submissões têm consequência legal. Instruções em prompt não são controle de segurança.

## Decisão
Toda tool do agente é registrada com um **nível de permissão**, aplicado por código (policy) antes da execução:

| Nível | Exemplos | Execução |
| --- | --- | --- |
| `read` | ler commits, PRs, eventos do ledger | automática |
| `write_internal` | criar rascunho, abrir pendência, anexar evidência | automática + audit log |
| `external` | criar issue/comentário no GitHub, enviar mensagem | configurável por tenant (padrão: requer aprovação) |
| `formal` | aprovar registro, confirmar dispêndio, marcar enquadramento, submeter | **sempre humano**; o agente não recebe essas tools |

## Consequências
- **Positivas:** segurança verificável e testável; autonomia onde é seguro.
- **Negativas:** mais cliques de aprovação em ações externas no início.
- **Regras derivadas:**
  - Tool sem nível declarado não é registrada (falha na inicialização).
  - Ações `formal` existem apenas como endpoints humanos autenticados.
  - Toda execução de tool gera registro em `audit` (quem, o quê, entrada resumida, resultado).
  - O sistema nunca afirma elegibilidade nem garante benefício fiscal; usa "potencialmente qualificável, sujeito a análise".

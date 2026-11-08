# ADR-0004: Agentes Maker–Checker com modelos diferentes

- **Status:** aceita (Maker no Featherless por padrão: ver proposta ADR-0013)
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
As fontes sugeriam de 4 a 6 agentes especializados. Muitos agentes aumentam custo, sobreposição e imprevisibilidade. Por outro lado, um único orquestrador que valida o próprio trabalho tende a não perceber os próprios erros — a equipe exigiu validação independente por **outro modelo**.

## Opções consideradas
1. Um orquestrador único
2. Multi-agente com supervisor (5–6 agentes)
3. **Maker–Checker**: um agente executor + um verificador independente de outro modelo, com checagens determinísticas antes

## Decisão
Opção 3.

- **Maker** (Claude, via SDK `anthropic` com tool use): investiga fontes, rascunha registros de atividade e justificativas, abre pendências. As especializações (documentação, conformidade, comunicação) são **tools e prompts por tarefa**, não agentes separados.
- **Checks determinísticos** (código, antes de qualquer LLM): schema válido; toda citação aponta para evidência existente do mesmo tenant; horas/valores/pessoas só vêm de eventos de origem formal; nenhum enquadramento afirmado como definitivo.
- **Checker** (outro provedor — ex.: OpenAI ou Google — atrás da interface `Verifier`; fallback configurável: outro modelo Claude com contexto limpo): recebe **somente o artefato + evidências citadas**, nunca o raciocínio do Maker. Retorna JSON validado por Pydantic: `verdict` (`pass|fail`), `issues[]`, `unsupported_claims[]`.
- Falha determinística → Maker refaz (máx. 2 tentativas). Discordância do Checker → `needs_human`.
- Checker roda **apenas em artefatos formais** (registro de atividade, justificativa técnica, itens de dossiê).

## Consequências
- **Positivas:** detecção de alucinação por modelo com vieses diferentes; arquitetura simples; custo controlado.
- **Negativas:** dois provedores (duas chaves, duas latências); necessidade de manter o prompt do Checker.
- **Regras derivadas:**
  - Novo "agente" só com nova ADR justificando isolamento de contexto ou paralelismo.
  - O modelo e versão usados por Maker e Checker são registrados no evento do ledger.
  - Prompts versionados em arquivo (`backend/src/basho/agent/prompts/`), nunca strings soltas no código.

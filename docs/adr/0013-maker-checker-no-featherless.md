# ADR-0013: Maker e Checker no Featherless (API compatível com OpenAI)

- **Status:** proposta (decisão de custo de 2026-11-08; aceite da equipe pendente)
- **Data:** 2026-11-08
- **Decisores:** equipe Basho (decisão de custo de Thiago Lorhan, 2026-11-08)
- **Altera:** ADR-0004 (item "Maker = Claude via SDK `anthropic`")

## Contexto e problema
A API da Anthropic é cobrada à parte, por uso, em dólar, e não faz parte do plano da equipe. O
Checker já roda no Featherless (OpenAI-compatível). Para a demo e o MVP, o orçamento é de
US$ 25 em créditos do Featherless.

## Opções consideradas
1. Manter o Maker no Claude (exige pagar a API da Anthropic).
2. **Maker também no Featherless**, por um adaptador com a mesma interface do SDK, mantendo o
   Claude como opção de configuração.

## Decisão
Opção 2.

- `MAKER_PROVIDER=featherless` usa `OpenAICompatibleMessagesClient`
  (`agent/openai_compat.py`): mesma interface `messages.create` que o Maker já usa, traduzida
  para `/chat/completions` com tool calling. Loop do Maker, policy, audit e ledger não mudam.
  `MAKER_PROVIDER=anthropic` continua disponível.
- **Modelos diferentes** (regra da ADR-0004 mantida e validada no startup): Maker
  `deepseek-ai/DeepSeek-V3.1`; Checker `zai-org/GLM-4.6`; fallback do Checker
  `moonshotai/Kimi-K2-Instruct-0905` (`CHECKER_FALLBACK_MODEL`, também diferente do Maker).
- Escolha por teste em 2026-11-08 com a tool `ledger_query_events`: os três chamaram a tool
  com argumentos corretos, devolveram JSON válido citando os ids e mantiveram um resultado
  negativo apesar de instrução injetada no conteúdo da evidência. DeepSeek-V3.1 tem o menor
  preço (US$ 0,285/1M entrada, US$ 1/1M saída) e contexto de 131k; Kimi-K2 tem contexto de 32k.
- **Segunda conta** (`FEATHERLESS_FALLBACK_API_KEY`): se a chave em uso responder 401/402/403
  (sem crédito, inválida), o Maker passa para a de fallback e repete a chamada; o Checker tenta,
  em ordem, o modelo do Checker em cada conta e depois o modelo de fallback em cada conta. 429
  (concorrência) não troca de conta. Logs registram só o índice da chave, nunca o valor.
- Raciocínio `<think>...</think>` é removido da resposta: o Checker nunca vê raciocínio do Maker.

## Consequências
- **Positivas:** custo estimado de ~US$ 0,02 por relatório (~1.000 relatórios com US$ 25); um
  só provedor e uma só chave; Claude segue como opção.
- **Negativas / custos:** modelos abertos variam mais em tool calling e disponibilidade (503
  "at capacity"); sem cache de prompt da Anthropic; dois modelos do mesmo provedor reduzem a
  independência de infraestrutura (mantida a de modelo/família).
- **Regras derivadas:** trocar de modelo exige repetir o teste de tool calling; o Checker e o
  fallback nunca podem ser o modelo do Maker (validado em `Settings`).

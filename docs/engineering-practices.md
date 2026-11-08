# Práticas de engenharia do Basho

Regras obrigatórias para humanos e agentes que contribuem com o repositório.

## Fluxo de trabalho
- **Uma issue → uma branch → um PR.** Branch: `<tipo>/<numero>-<slug>` (ex.: `feat/12-evidence-ledger`).
- **Conventional Commits:** `feat|fix|refactor|docs|test|chore|perf|ci(<escopo>): descrição`. Escopos = módulos (`evidence`, `agent`, `web`, `infra`…).
- Nunca commitar direto na `main`. PR exige CI verde e ao menos 1 revisão.
- PR descreve: o quê, por quê, issue (`Closes #N`), ADRs afetadas, plano de teste.

## Decisões de arquitetura
- Mudou algo estrutural (módulo, dependência relevante, fluxo do agente, modelo de dados do ledger, política de segurança)? **Crie uma ADR** a partir de [`adr/0000-template.md`](adr/0000-template.md) no mesmo PR.
- ADR aceita não é editada; é **substituída** por outra ADR.

## Código
- Python: `ruff` (lint + format), `mypy` (strict em `domain/`), type hints em tudo público.
- TypeScript: `strict: true`, sem `any`, validação Zod de dados externos.
- Funções < 50 linhas, arquivos < 800 linhas, aninhamento ≤ 4 níveis (use early return).
- **Imutabilidade por padrão:** dataclasses `frozen=True`/modelos Pydantic imutáveis no domínio; retornar novas instâncias.
- Sem números mágicos: constantes nomeadas ou configuração.
- Erros tratados explicitamente; nunca engolir exceção. Mensagens ao usuário sem detalhes internos.
- Sem `print`/`console.log` — use o logger estruturado.

## Testes
- Padrão AAA (Arrange, Act, Assert), nomes descritivos.
- Obrigatórios: regras de domínio, policy de tools, checks determinísticos do agente, isolamento de tenant (RLS), imutabilidade do ledger.
- Chamadas a LLM em testes: **mockadas** por padrão; testes reais marcados `@pytest.mark.llm` e fora do CI padrão.
- Bug corrigido = teste que reproduz o bug.

## Segurança (checklist de PR)
- [ ] Sem segredos no código ou em logs
- [ ] Entrada validada na borda
- [ ] Queries parametrizadas (ORM), sem SQL concatenado
- [ ] `tenant_id` respeitado / RLS ativa
- [ ] Conteúdo externo tratado como dado para o LLM
- [ ] Ações `formal` só via endpoint humano
- [ ] `/security-review` rodado se tocar auth, banco, conectores ou LLM

## Agente e LLM
- Prompts versionados em `backend/src/basho/agent/prompts/`.
- Toda saída de LLM consumida por código é validada por schema Pydantic.
- Registrar modelo, versão, tokens e latência por chamada (observabilidade de custo).
- Prompt caching para instruções fixas e definições de tools.

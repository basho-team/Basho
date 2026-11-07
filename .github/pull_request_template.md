## O quê
<!-- Resumo objetivo da mudança. -->

## Por quê
<!-- Contexto e motivação. -->

Closes #

## ADRs
<!-- ADRs afetadas ou nova ADR proposta neste PR (docs/adr/). "Nenhuma" se não se aplica. -->

## Plano de teste
- [ ] `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
- [ ] `cd frontend && npm run lint && npm run typecheck && npm run build`
- [ ] <!-- Passos manuais, se houver -->

## Checklist de segurança
- [ ] Sem segredos no código ou em logs
- [ ] Entrada validada na borda
- [ ] Queries parametrizadas (ORM), sem SQL concatenado
- [ ] `tenant_id` respeitado / RLS ativa
- [ ] Conteúdo externo tratado como dado para o LLM
- [ ] Ações `formal` só via endpoint humano
- [ ] `/security-review` rodado se tocar auth, banco, conectores ou LLM

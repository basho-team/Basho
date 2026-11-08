# Demonstração do Basho — runbook

Projeto sintético, tudo marcado `is_synthetic` (nenhum dado formal). O sistema **apoia a
análise**: não decide enquadramento nem garante benefício fiscal.

## Subir (Windows)

Pré-requisitos: Docker Desktop ligado, `uv` e Node instalados.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1        # sobe tudo
powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1 -Down  # derruba e limpa
```

O script cria um Postgres descartável (porta 55499), aplica as migrações, cria os logins de
menor privilégio (`basho_api_login`/`basho_worker_login`), roda o seed (`python -m basho.seed`,
idempotente), sobe a API (`python -m basho.serve`, 8010) e o front em modo `api` (3010).
Se a pasta do front já tem `node_modules`, ele não reinstala.

> No Windows use `python -m basho.serve` (e não `uvicorn`): o psycopg assíncrono exige
> `SelectorEventLoop`. O `uvicorn.exe` também pode ser bloqueado por política de aplicativos.

## O projeto da demo

**Demo — Quantização de modelos de detecção de falhas**, com duas atividades:

| Atividade | Estado do artefato | O que a tela mostra |
| --- | --- | --- |
| Quantização do modelo | `verified` pelo Checker | Pendência de **aprovação** do gerente |
| Rebalanceamento do dataset (SMOTE) | `needs_human` | Divergência do Checker + 2 lacunas que o Maker não preencheu |

## Roteiro (≈ 4 min)

1. **Gerente → Pendências** (`/gerente/pendencias`): 4 pendências derivadas do ledger; a de
   aprovação é do gerente, as de justificativa são do pesquisador/coordenador.
2. **Pesquisador → Pendências** (`/pesquisador/pendencias`): responder a justificativa do SMOTE
   grava uma `user_correction` (o original não muda) e marca dependentes como `needs_review`.
3. **Gerente aprova** o registro verificado: ação **formal, só humano** (pesquisador recebe 403).
4. **Dossiê** (`/gerente/dossie`): fontes (commits), vereditos do Checker, histórico e decisão.
5. Ponto de arquitetura: o agente nunca recebe tool `formal`; toda afirmação cita evidência.

## Agente real (opcional)

O worker consome a fila de `agent_runs` e chama o Maker/Checker. Precisa de chaves reais
(`ANTHROPIC_API_KEY`, `FEATHERLESS_API_KEY`, `FEATHERLESS_BASE_URL`, `CHECKER_MODEL`) e do login do
worker (`basho_worker_login`):

```powershell
$env:DATABASE_URL = "postgresql+psycopg://basho_worker_login:worker_demo@127.0.0.1:55499/basho"
cd backend; uv run python -m basho.agent.worker
```

Disparar um run (a UI ainda não tem esse botão; não há rota no BFF):

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects/<project_id>/agent-runs \
  -H "content-type: application/json" -H "Idempotency-Key: demo-0001" \
  -H "X-Basho-Identity-Secret: demo-secret-with-at-least-32-chars-ok-1" \
  -H "X-Basho-User-Id: 22222222-2222-4222-8222-222222222222" -H "X-Basho-Role: researcher" \
  -d '{"researcher_id":"22222222-2222-4222-8222-222222222222","period":{"start":"2026-10-01","end":"2026-10-31","timezone":"America/Sao_Paulo","periodicity":"monthly"}}'
# acompanhar: GET /api/v1/agent-runs/<run_id> (estado, tentativas, custo, latência)
```

## Limites conhecidos (não esconda na demo)

- A UI em modo `api` implementa pendências, aprovação, revisão e dossiê; consolidação, fiscal,
  `getRun` e `triggerClosing` ainda dão `NOT_IMPLEMENTED` (use o modo `mock` para essas telas).
- Run do worker preso em `running` após queda do processo não é recuperado (backlog).
- Identidade do revisor é placeholder do BFF (#47): não publique o deploy sem camada de acesso.

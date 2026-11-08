# Deploy público (Converge)

Dois sites, todos com dados **sintéticos** (`is_synthetic`):

| Site | Onde | Modo | Acesso |
| --- | --- | --- | --- |
| Demo navegável | Vercel, projeto `basho-demo` | `mock` | aberto |
| App com backend real | Railway, serviço `web` | `api` | Basic Auth (`DEMO_BASIC_AUTH_USER/PASSWORD`) |

## Railway (projeto `basho`)

| Serviço | Origem | `BASHO_PROCESS` | Banco |
| --- | --- | --- | --- |
| `Postgres` | plugin | — | — |
| `migrate` | `backend/` (Dockerfile) | `migrate` | dono (`MIGRATION_DATABASE_URL`) |
| `api` | `backend/` (Dockerfile) | `api` | `basho_api_login` |
| `worker` | `backend/` (Dockerfile) | `worker` | `basho_worker_login` |
| `web` | `frontend/` (Railpack) | — | via BFF → `api` |

- `migrate` é one-shot: `alembic upgrade head`, `python -m basho.provision` (cria/atualiza os
  logins de menor privilégio a partir de `API_DB_PASSWORD`/`WORKER_DB_PASSWORD`) e, com
  `RUN_SEED=1`, `python -m basho.seed` como `basho_api_login`. Tudo idempotente.
- Só o `migrate` recebe a URL do dono; `api` e `worker` nunca (ADR-0006). A API aborta o
  startup se o login ignorar a RLS.
- As URLs usam referências do Railway (`${{Postgres.PGHOST}}`, `${{migrate.API_DB_PASSWORD}}`),
  então nenhum segredo fica no repositório.
- Chaves de LLM e GitHub reais só no `worker`; a API usa placeholders (não chama LLM).

## Variáveis do `web` (modo api)

`NEXT_PUBLIC_DATA_SOURCE=api`, `BASHO_API_URL`, `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_BASHO_PROJECT_ID` (impresso pelo seed), `REVIEWER_IDENTITY_SECRET=${{api.REVIEWER_IDENTITY_SECRET}}`,
`BASHO_DEMO_REVIEWERS`, `DEMO_BASIC_AUTH_USER`, `DEMO_BASIC_AUTH_PASSWORD`.

Sem as credenciais de Basic Auth, o `src/proxy.ts` deixa o modo `mock` aberto e **fecha** o
modo `api` (503). Depois do portão do deploy, o proxy ainda exige a sessão individual do login
por função (#68, ADR-0011 proposta): uma camada não substitui a outra.

## Login por função (os dois sites)

| Variável | Vercel | Railway `web` |
| --- | --- | --- |
| `BASHO_DEMO_LOGIN_ENABLED` | `true` | `true` |
| `BASHO_DEMO_PASSWORD_HASH` | `scrypt:<salt>:<hash>` | idem |
| `BASHO_DEMO_SESSION_SECRET` | ≥ 32 caracteres (sessão assinada: sem disco compartilhado) | — (sessão em arquivo, revogável) |
| `BASHO_DEMO_BACKEND_USERS` | — | `{"ana":"<uuid pesquisador>","marina":"<uuid gerente>"}` (UUIDs do seed) |

No Vercel o disco é somente leitura e não é compartilhado entre instâncias; sem
`BASHO_DEMO_SESSION_SECRET` o login responde 500. A sessão assinada não tem revogação no
servidor (logout apaga o cookie; um token copiado vale até expirar, ≤ 4 h).

A origem esperada nas rotas POST vem de `X-Forwarded-Proto/Host` (`publicOrigin`), porque
atrás do proxy `request.url` é o endereço interno do container.

## Atualizar

- Manual: `railway up backend --path-as-root --service <api|worker|migrate>` e
  `railway up frontend --path-as-root --service web`; Vercel: `vercel deploy --prod` em `frontend/`.
- Automático: em cada serviço do Railway, *Settings → Source → Connect Repo* `basho-team/Basho`,
  branch `main`, *Root Directory* `backend` (ou `frontend` no `web`).

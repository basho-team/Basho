# Demonstração do Basho — runbook

Projeto sintético, tudo marcado `is_synthetic` (nenhum dado formal). O sistema **apoia a
análise**: não decide enquadramento nem garante benefício fiscal.

## Subir (Windows)

Pré-requisitos: Docker Desktop ligado, `uv` e Node instalados.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1                  # sobe tudo (Drive/Notion reais)
powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1 -FakeProviders   # ensaio sem credenciais
powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1 -Down            # derruba e limpa
```

O script cria um Postgres descartável (porta 55499), aplica as migrações, cria os logins de
menor privilégio (`basho_api_login`/`basho_worker_login`), roda o seed (`python -m basho.seed`,
idempotente), sobe a API (`python -m basho.serve`, 8010), o **worker** (publica nos destinos e roda o
agente) e o front em modo `api` (3010).
Se a pasta do front já tem `node_modules`, ele não reinstala.

> No Windows use `python -m basho.serve` (e não `uvicorn`): o psycopg assíncrono exige
> `SelectorEventLoop`. O `uvicorn.exe` também pode ser bloqueado por política de aplicativos.

## Login (ADR-0011)

A demo exige login local por função. O `demo-up.ps1` configura o login com uma senha de demonstração
(`-DemoPassword`, padrão `basho-demo-2026`, guardada só como hash scrypt) e mapeia as contas aos
usuários do backend. Contas fictícias, todas com a mesma senha:

| Conta | Função | Vê |
| --- | --- | --- |
| `ana@lumen.example` | Pesquisador | seus relatórios e pendências |
| `marina@lumen.example` | Gerente | gestão, dossiê, **Publicação** (autorizar links, gerar e publicar) |
| `rafael@lumen.example` | Fiscal | análise fiscal |

> **Abra `http://localhost:<porta>` (não `127.0.0.1`).** O login confere a origem exata, e o Next
> monta a URL da requisição com `localhost`; pelo `127.0.0.1` o login é recusado.

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

## Publicar nas suas pastas (Drive e Notion) — o fluxo do produto

O gerente cola **um link com permissão de edição** e o Basho passa a publicar os relatórios
verificados numa pasta `BASHO`, **sem aprovação de rotina** ([ADR-0010](adr/0010-publicacao-autonoma-drive-notion.md)).

**Preparação (uma vez, antes da demo):**

1. *Drive*: crie uma service account no Google Cloud (API do Drive ativada) e uma chave JSON.
   Defina `GOOGLE_SERVICE_ACCOUNT_JSON` com o JSON (ou o caminho do arquivo) **antes** de rodar o
   `demo-up.ps1`. **Compartilhe a pasta do Drive como Editor com o e-mail da service account**
   (a tela Publicação mostra esse e-mail). Um link "qualquer pessoa edita" não autentica a API.
2. *Notion*: crie uma integração interna, defina `NOTION_TOKEN` e, na página, abra `•••` → Conexões e
   adicione a integração.
3. Opcional: `GITHUB_TOKEN` real para o Basho ler commits e PRs do repositório colado.

**Na tela** (`/gerente/publicacao`, papel gerente; as prévias sintéticas ficam em `/integracoes`):

1. Cole o link da pasta do Drive → *Conectar*. O Basho confere o acesso; se faltar permissão, a
   mensagem diz com quem compartilhar. Links de hosts desconhecidos são recusados.
2. Cole o link da página do Notion e, se quiser, o do repositório do GitHub.
3. *Publicar agora*: o worker cria `BASHO/Relatório BASHO — … — <id>` na pasta e na página, com
   afirmações citando commits, incerteza explícita e as pendências que dependem de uma pessoa.
   Repetir não duplica; revogar um link interrompe novas publicações.
4. Depois que o agente gera um artefato `verified`, a publicação acontece sozinha.

**Ensaio sem credenciais:** `-FakeProviders` sobe um servidor FALSO de Drive/Notion; os documentos
gerados abrem no navegador (`http://127.0.0.1:9100/doc/<id>`, `/notion/<id>`, `/_state`). Cole
qualquer link de pasta/página válido no formato (ex.:
`https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345`). Não é a integração real.

## Agente real (opcional)

O worker consome a fila de `agent_runs` e chama o Maker/Checker. Precisa de chaves reais
(`ANTHROPIC_API_KEY`, `FEATHERLESS_API_KEY`, `FEATHERLESS_BASE_URL`, `CHECKER_MODEL`) e do login do
worker (`basho_worker_login`):

```powershell
$env:DATABASE_URL = "postgresql+psycopg://basho_worker_login:worker_demo@127.0.0.1:55499/basho"
cd backend; uv run python -m basho.agent.worker
```

Disparar um run (a UI ainda não tem esse botão; não há rota de agent-runs no BFF):

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects/<project_id>/agent-runs \
  -H "content-type: application/json" -H "Idempotency-Key: demo-0001" \
  -H "X-Basho-Identity-Secret: demo-secret-with-at-least-32-chars-ok-1" \
  -H "X-Basho-User-Id: 22222222-2222-4222-8222-222222222222" -H "X-Basho-Role: researcher" \
  -d '{"researcher_id":"22222222-2222-4222-8222-222222222222","period":{"start":"2026-10-01","end":"2026-10-31","timezone":"America/Sao_Paulo","periodicity":"monthly"}}'
# acompanhar: GET /api/v1/agent-runs/<run_id> (estado, tentativas, custo, latência)
```

## Limites conhecidos (não esconda na demo)

- Publicação: um relatório novo vira **novo documento** (o anterior fica; não há edição em lugar nem
  remoção). Service account não tem cota no Drive pessoal: Google Docs funcionam, binários podem
  falhar fora de Drive compartilhado. Notion limita ~3 req/s.
- Não foi testado contra o Google/Notion reais (só contra transporte simulado e o servidor falso).
- A UI em modo `api` implementa pendências, aprovação, revisão e dossiê; consolidação, fiscal,
  `getRun` e `triggerClosing` ainda dão `NOT_IMPLEMENTED` (use o modo `mock` para essas telas).
- Run do worker preso em `running` após queda do processo não é recuperado (backlog).
- Identidade do revisor é placeholder do BFF (#47): não publique o deploy sem camada de acesso.

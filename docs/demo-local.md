# Demo local do Basho (Converge Challenge 2026)

Jornada: **Pesquisador** registra atividade → associa evidências → constrói relatório → recebe verificações → corrige → confirma a versão exata → **Gerente** consolida → **Fiscal** consulta o dossiê rastreável.

## Subir

Pré-requisitos: Docker, `uv`, Node 24 (`.nvmrc` 26 também serve), portas livres 55432/8765/3765.

```bash
scripts/demo/up.sh                 # banco NOVO basho_demo_<carimbo> + migrações + seed + API + web
DEMO_REBUILD=1 scripts/demo/up.sh  # idem, refazendo o build do frontend
```

Abre em **http://127.0.0.1:3765** (API em http://127.0.0.1:8765, docs em `/docs`).
Cada execução cria um banco novo; nenhum banco é apagado. Segredos locais gerados em
`~/.basho-demo-secrets` (ou `DEMO_SECRETS`); logs em `.demo-logs/`.

## O que é real e o que é sintético

| Peça | Situação |
|---|---|
| Ledger append-only, RLS por tenant, roles de menor privilégio (#40, #46) | **real** (Postgres 16) |
| Versões imutáveis, correção = nova versão, revisão pela versão exata com 409 (#48) | **real** |
| Checks determinísticos (#45): evidência inexistente, horas/valores no texto, elegibilidade afirmada, injeção | **real** |
| Consolidação gerencial e texto exportável; dossiê fiscal com hash e localizador de cada evidência | **real** |
| Projeto, período e pessoas (Ana, Bia, Carla, Davi) | **sintéticos**, constantes em `backend/src/basho/demo/context.py` |
| Eventos de GitHub e horas de RH de Bia; relatório v1 de Bia | **sintéticos** (seed `python -m basho.demo.seed`, ator `system:demo-seed`) |
| Identidade | **demonstração**: a persona escolhida no topo vai num cookie; o BFF a afirma à API com `REVIEWER_IDENTITY_SECRET`. Não é autenticação (#47). |
| Rascunho do relatório | **automático por regras** (`POST .../reports/auto-draft`, ator `system:auto-draft:regras-v1`): só reproduz e cita as fontes do pesquisador; o que falta vira pergunta. Ponto de troca para o Maker. |
| Maker (Claude) e Checker (outro provedor) | **implementados e testados com LLM simulado (#49, #45)**, mas **não acionados pela interface**: sem chave de API e sem custo. A tela mostra "indisponível". |

## Roteiro (≈5 min) — o sistema prepara, a pessoa lê e só edita se algo estiver errado

1. **Abertura**: banner de dados sintéticos; "o Basho não decide enquadramento nem garante benefício".
2. **Ana — Pesquisador**: a tela abre com o **rascunho já preparado** a partir do ledger (cada afirmação cita a fonte; hipótese, desfechos e horas viram perguntas) e com as **verificações já rodadas**. Rótulo honesto: "regras; IA indisponível nesta demo".
3. **Edição sutil**: Ana nota que falta o resultado negativo → "Algo errado? Editar" → acrescenta o experimento **negativo** citando o commit c94ab → **v2** (a v1 continua em "Versões").
4. **Conflito**: abre a v1 e tenta "Confirmar v1" → **409**, nada gravado; "Abrir a versão atual" → "Confirmar v2".
5. **Carla — Gerente**: "registrar horas formais de um pesquisador" (link discreto) para a Ana. **Ana** edita: resolve a lacuna `formal_hours` citando o registro → **v3** → confirma.
6. **Bia**: lê e confirma o próprio relatório (conflito entre bancadas, resultado inconclusivo).
7. **Carla**: consolidação (Negativos 1 / Inconclusivos 1), origem de cada item, texto exportável; "Aceitar v3".
8. **Davi — Fiscal**: dossiê só leitura — situação de cada item, hash e localizador `report:<versão>/<tipo>/<item>`, revisão do pesquisador pelo ID, horas por referência formal. "Material para análise humana; não é aprovação fiscal."

**Frases proibidas:** "é elegível", "garante o benefício", "aprovado fiscalmente", "envia o FORMP&D".

## Testes

```bash
# backend (Postgres real): defina TEST_DATABASE_URL com o role dono
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && REQUIRE_DB_TESTS=1 uv run pytest
# frontend
cd frontend && npm run lint && npm run typecheck && npm run build
# e2e na interface (com a demo no ar, banco novo): Chromium/Chrome local, sem dependências
BASHO_E2E_BROWSER=/caminho/chrome node frontend/tests/e2e-journey.mjs   # capturas em frontend/.qa/
```

## Limitações conhecidas

- Sem autenticação real; troca de persona é demonstração. Um único tenant.
- Maker/Checker por LLM não acionados pela interface (sem chave). O conector GitHub (#7) não existe: eventos de GitHub são do seed.
- Sem cadastro de projetos/pessoas (constantes sintéticas). Período fixo (outubro/2026).
- O dossiê procura substituições (`supersedes`) nos 200 eventos mais recentes do projeto.
- Revisão do gerente usa o mesmo endpoint de revisão; não há fluxo de "encaminhar ao fiscal" nem decisão fiscal registrada.
- Relatórios criados pela interface são marcados `is_synthetic` (ambiente de demonstração).

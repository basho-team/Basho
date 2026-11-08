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
| Maker (Claude) e Checker (outro provedor) | **implementados e testados com LLM simulado (#49, #45)**, mas **não acionados pela interface**: sem chave de API e sem custo. A tela mostra "indisponível". |

## Roteiro (≈5 min)

1. **Abertura** (página inicial): banner de dados sintéticos; "o Basho não decide enquadramento nem garante benefício".
2. **Ana — Pesquisador**: registra a atividade "Avaliação do int8"; monta o relatório com duas afirmações (uma com "40 horas" no texto), um experimento **negativo** e sem horas formais (abre a lacuna `formal_hours`). Cria a **v1**.
3. **Verificações**: "Rodar verificações" → reprovado com `formal_data_in_text`. "Checker por IA indisponível" aparece explícito.
4. **Correção**: revisa a afirmação sem horas → **v2** (a v1 continua visível em "Versões").
5. **Conflito**: abre a v1 e tenta "Confirmar v1" → **409**, nada gravado; "Abrir a versão atual" → "Confirmar v2".
6. **Carla — Gerente**: registra as horas formais da Ana (coordenação). **Ana** resolve a lacuna citando o registro → **v3** → confirma a v3.
7. **Bia**: confirma o próprio relatório (que tem conflito entre bancadas e resultado inconclusivo).
8. **Carla**: consolidação com Negativos 1 / Inconclusivos 1, origem de cada item (pessoa, versão, item, texto confirmado), "Ver texto exportável"; "Aceitar v3".
9. **Davi — Fiscal**: dossiê com situação de cada item (sustentada, pendente, conflitante, negativo, inconclusivo, lacuna), hash e localizador `report:<versão>/<tipo>/<item>`, revisão do pesquisador pelo ID e horas por referência formal. Fecha com: "material para análise humana; não é aprovação fiscal".

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

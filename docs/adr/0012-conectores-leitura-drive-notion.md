# ADR-0012: Conectores de leitura Google Drive e Notion (evidências)

- **Status:** proposta (decisão de produto de 2026-11-08; aceite da equipe pendente)
- **Data:** 2026-11-08
- **Decisores:** equipe Basho (decisão de produto de Thiago Lorhan, 2026-11-08)
- **Altera:** ADR-0007 (item "Fora: outros conectores")
- **Relação:** complementa a ADR-0010 (publicação em Drive/Notion, escrita a partir de links autorizados). Esta trata só da **leitura** de evidências.

## Contexto e problema
A ADR-0007 limitou o MVP ao GitHub. Mas boa parte das evidências de P&D (planos de
experimento, diários, atas, resultados, planilhas de benchmark) mora no Google Drive e no
Notion. Sem essas fontes, o relatório do pesquisador e o dossiê do fiscal ficam presos ao que
aparece em commits e PRs. Em 2026-11-08 o produto decidiu integrar Drive e Notion além do
GitHub.

## Opções consideradas
1. Manter só GitHub e upload manual de documentos.
2. Tools novas do Maker que leem Drive/Notion em tempo real.
3. **Ingestão no ledger antes do Maker** (como o GitHub), só leitura, com a revisão do
   documento como unidade de evidência.

## Decisão
Opção 3.

- `basho.connectors.google_drive` (OAuth com refresh token, escopo `drive.readonly`) e
  `basho.connectors.notion` (token de integração interna) **só leem**. Nenhuma escrita
  externa nova; a única ação externa continua `github_create_issue`, com aprovação (ADR-0005).
- O mapa projeto → pasta do Drive / database ou página do Notion vem da configuração
  (`GOOGLE_DRIVE_PROJECT_FOLDERS`, `NOTION_PROJECT_SOURCES`), nunca do modelo. IDs são
  validados no startup.
- Cada **revisão** vira um evento `document_observed` (`source` = `google_drive` | `notion`,
  `source_ref` = `<doc_id>@<revisão>`), com texto truncado e `content_sha256` do conteúdo lido.
  PDFs e imagens entram só com metadados e o checksum da fonte.
- Revisão nova de um documento já registrado é um evento novo com `supersedes` = revisão
  anterior (o original nunca muda, ADR-0003) e dispara a propagação do #11: relatório que citava
  a revisão antiga vai para `needs_review`.
- O worker sincroniza as fontes do projeto antes do Maker, em transações curtas próprias. O
  Maker encontra os documentos via `ledger_query_events` (sem tool nova, sem mudar a policy).
  Texto do documento é **dado** e só chega ao modelo em `untrusted_data` (ADR-0006).
- Falha da fonte vira `RunError` com código estável (`google_drive_*`, `notion_*`), sem chamar
  o LLM; `retryable` para rate limit, rede e 5xx.

## Consequências
- **Positivas:** evidência de documentos rastreável até a revisão exata; documento alterado
  depois de citado é detectado e reabre a revisão humana; mesmo modelo de segurança do GitHub.
- **Negativas / custos:** sem webhooks (a sincronização acontece por run); Drive só lê o
  primeiro nível da pasta e Notion só os blocos de primeiro nível; refresh token do Drive é um
  segredo a mais para gerenciar; documentos sem texto extraível (PDF) não são lidos pelo Maker.
- **Regras derivadas:** novos valores de `EventKind`/`EventSource` exigem migração que redefina
  os CHECKs do ledger (0009) e o teste de drift aponta para a migração mais recente que os
  define. Conector novo só lê, salvo ADR que diga o contrário.
- **Convivência com a ADR-0010:** a publicação autentica no Google por service account e a
  leitura, por OAuth com refresh token (a conta do usuário lê as pastas dele sem compartilhar com
  a service account). O `NOTION_TOKEN` é o mesmo. Próximo passo natural: a leitura usar os links
  autorizados de `project_links` (ADR-0010) em vez dos mapas `GOOGLE_DRIVE_PROJECT_FOLDERS` e
  `NOTION_PROJECT_SOURCES`, e unificar a autenticação do Google.
- **Backlog:** subpastas e blocos aninhados; OCR/texto de PDF; webhooks; mapa projeto → fontes
  guardado no banco em vez de env; reconciliação de documentos financeiros.

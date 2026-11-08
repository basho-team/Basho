# ADR-0010: Publicação autônoma em Drive e Notion a partir de links autorizados

- **Status:** proposta (implementação entregue atrás de links explícitos; aceite da equipe pendente)
- **Data:** 2026-11-08
- **Decisores:** equipe Basho — direção de produto dada por Vitor em 2026-11-08; revisão pendente
- **Escopo:** concretiza o primeiro corte da [ADR-0008](0008-autonomia-documental-lei-do-bem.md) (autonomia documental) e usa a exceção de ação externa já prevista na [ADR-0005](0005-gates-de-permissao-e-aprovacao-humana.md). Não altera 0001–0004, 0006 e 0007.

## Contexto e problema

A ideia do produto é que o usuário **cole um link com permissão de edição** (pasta do Google Drive,
página do Notion, repositório do GitHub) e o Basho gere e organize os relatórios sozinho, numa
pasta chamada `BASHO`, sem exigir que um humano aprove cada relatório de rotina. Hoje o fluxo aceito
(ADR-0007) lê só o GitHub, não escreve em lugar nenhum e abre uma pendência de aprovação para todo
artefato verificado. Isso contradiz a ideia e a ADR-0008, ainda em proposta, ainda não vale.

Há três forças em tensão: (1) autonomia de documentos de rotina; (2) o agente **nunca** recebe tool
`formal` nem inventa dado formal (CLAUDE.md, regras 3, 5 e 6); (3) escrever em sistema do usuário é
ação externa e exige autorização prévia do tenant (ADR-0005).

## Opções consideradas

1. **Manter a aprovação de todo artefato** e publicar só depois dela. Seguro, mas não é o produto.
2. **Dar ao agente uma tool `external` que escreve no Drive/Notion**, com a policy liberando destinos
   cadastrados. Mistura o raciocínio do modelo com um efeito externo e amplia a superfície de prompt
   injection.
3. **Passo determinístico depois do Checker**, executado pelo worker, que publica o artefato
   `verified` nos destinos cadastrados por um gerente. O agente não ganha tool nova.

## Decisão

Opção 3.

- **Autorização do tenant = cadastro do link.** `POST /projects/{id}/links` (só `manager`) recebe a URL,
  extrai só o **ID** (host em allowlist, https, sem credenciais; a URL colada nunca é requisitada,
  ADR-0006 contra SSRF), **verifica o acesso** com a credencial do Basho e só então grava em
  `project_links`. Revogar muda o status; nada é apagado.
- **Credenciais do Basho em variáveis de ambiente**: service account do Google
  (`GOOGLE_SERVICE_ACCOUNT_JSON`, o usuário compartilha a pasta com o e-mail dela como Editor) e token
  de integração do Notion (`NOTION_TOKEN`, o usuário adiciona a conexão na página). Um link com
  "qualquer pessoa pode editar" **não** autentica chamadas de API; por isso o passo de compartilhar é
  obrigatório, e a tela mostra com quem compartilhar.
- **Publicação como fila.** `publications` tem uma linha por (artefato × destino), idempotente por
  restrição de unicidade. O worker reserva com `FOR UPDATE SKIP LOCKED`, renderiza, escreve **sem
  transação aberta**, e registra o resultado. Falha transitória volta à fila com backoff (5 s·2ⁿ, teto
  5 min, 5 tentativas); permanente falha com código estável.
- **Antes de criar, procurar.** Drive e Notion são consultados pelo nome (`BASHO` e título do
  relatório, que leva o prefixo do ID do artefato): repetir após falha não duplica.
- **Só artefato `verified` ou `approved` é publicado**, e só se ainda for quando o worker rodar
  (corrigido ou rejeitado depois de enfileirar → não publica). O que falta ou diverge segue como
  pendência (`missing[]`, `needs_human`) e aparece no documento como "Pendências para os responsáveis".
- **A aprovação formal continua existindo** (`approved`/`rejected`, só `manager`), mas deixa de ser
  pré-requisito de publicação de documento. Ela segue reservada a decisões que pedem responsável.
- **Conteúdo externo é dado**: mensagens de commit e títulos de PR vão escapados no HTML e como texto
  puro nos blocos do Notion. O texto do relatório mantém "potencialmente qualificável, sujeito a
  análise" e o aviso de que o Basho não decide enquadramento nem submete o FORMP&D.
- **Dados**: `project_links` e `publications` têm `tenant_id` + RLS forçada, `GRANT` por coluna e nenhum
  `DELETE`. A API cria links; só o worker grava o resultado das publicações.

## Consequências

- **Positivas:** documento de rotina sai sem fila de aprovação; autorização explícita e revogável por
  destino; nenhum efeito externo dentro do raciocínio do modelo; retomada e idempotência testadas.
- **Negativas / custos:** o usuário precisa compartilhar a pasta com a service account (limitação de
  API, não de produto). Service accounts não têm cota no Drive pessoal: Google Docs nativos funcionam,
  mas arquivos binários podem falhar fora de Drive compartilhado. O Notion limita ~3 req/s por
  integração. Nova versão de um relatório vira **novo documento** (o anterior permanece); não há
  edição em lugar nem remoção.
- **Regras derivadas:** (a) publicação externa só pelo worker, em link ativo cadastrado por `manager`,
  nunca como tool do agente; (b) todo link passa por `parse_link` e verificação de acesso antes de
  gravar; (c) credenciais só em ambiente; (d) teste novo de destino usa `Destination` falso, nunca a
  rede. Atualizar o CLAUDE.md quando esta ADR for aceita; até lá, a regra 1 é cumprida por esta ADR e
  por `docs/architecture.md` §Publicação.
- **Pendente:** aceite da equipe; migração `0008` (a `0007` está reservada à ponte agente→revisão);
  consolidação gerencial e pacote fiscal publicados em Drive/Notion; ciclo de exceção no Notion
  (criar tarefa para pendência) — próximos cortes.

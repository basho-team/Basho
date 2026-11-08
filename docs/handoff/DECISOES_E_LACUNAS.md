# Decisões e lacunas — snapshot 07/11/2026

## Confirmado pelo usuário

- Produto atende pesquisador, gerente e fiscal; automação burocrática e documental é central.
- Pesquisador recebe relatórios prontos para revisar/corrigir/validar.
- Gerente recebe consolidação, pode ajustar e discutir, encaminhando ao fiscal.
- Fiscal recebe documentação e sinalizações sobre condições relativas às atividades, com decisão fiscal humana.
- Lei do Bem é um recurso principal, sem substituir a operação mais ampla de P&D.
- Arquitetura passa a ser conduzida pelo ChatGPT nesta conversa, substituindo a atribuição anterior ao Claude de Carlos.
- Vitor é responsável pelo backend, conforme divisão de cinco executores.
- Carlos usa Claude Code para interface e apresentação.
- Thiago e Vitor têm Claude Code e Codex; Thiago utiliza Paperclip.
- Foi solicitada preparação do contexto das IAs; não houve implementação ou alteração do Paperclip nesta conversa.

## Base técnica proposta

React/TypeScript, FastAPI/Pydantic, PostgreSQL, LangGraph, worker, quatro responsabilidades lógicas de agentes, contratos versionados e primeiro fluxo vertical. Proposta pendente de inspeção do repositório; não é evidência de dependências instaladas.

## Correções que não podem se perder

- Não voltar à interpretação de que o produto é somente um gerador de pacote fiscal.
- Não usar a instrução histórica que reserva a arquitetura ao Claude de Carlos como decisão atual.
- Divisão antiga com Thiago responsável pelo núcleo foi substituída: Vitor tem backend e integração.
- Financeiro básico e retomada não são opcionais no cenário proposto.
- Drive foi posicionado após o primeiro ciclo; três conectores completos não devem bloquear a integração inicial.
- A aprovação de um relatório não significa aprovação fiscal; a sinalização não significa homologação.

## Pendências de contexto

| Item | Impacto | Quem deve informar/confirmar |
|---|---|---|
| URL do repo, branch e código existente | Reuso, distribuição de arquivos e contratos | Equipe/Carlos |
| Acesso dos três integrantes | Trabalho em branches e integração | Dono do repositório |
| Prazo e regulamento completo | Recorte e cronograma reais | Equipe |
| Provedor/modelo/runtime de IA | Execução do produto e custos | Equipe |
| Contas e escopos de integrações | Demo real e permissões | Donos dos ambientes |
| Ambiente de execução/deploy | Persistência e acessibilidade da demo | Vitor/Carlos |
| Layout fiscal e critérios cobertos | Limites corretos da exportação | Thiago com revisão fiscal pertinente |

Ferramentas de programação disponíveis não comprovam acesso API ao modelo dentro da aplicação. Não solicitar senhas em chat; usar configuração de segredos autorizada.

## Contexto Paperclip observado em capturas

Codex Executor pausado, configuração de laboratório restrita a repositório sintético. Claude Local Lab ocioso, instrução genérica. Skills visíveis: paperclip, complain, suggestion-box. Capturas não comprovam estado atual, autenticação válida, modelo efetivo do Claude nem acesso ao repo. Preparar adaptação depois de obter contexto atual; não sobrescrever arquivos automaticamente.

## Referências regulatórias e limites da verificação

Os relatórios originais estão em references/. A leitura integral foi realizada, incluindo diagramas do PDF. As referências abaixo são insumos para critérios, não autorização para prometer conformidade global.

- Lei 11.196/2005, texto atualizado na Câmara: https://www2.camara.leg.br/legin/fed/lei/2005/lei-11196-21-novembro-2005-539221-normaatualizada-pl.html
- Catálogo MCTI de legislação: https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/lei-do-bem/paginas/legislacao
- FORMP&D: https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/lei-do-bem/paginas/formulario-eletronico-formp-d/
- Novidades da edição 2026: https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/2026/06/mcti-lanca-formp-d-2026-e-lei-do-bem-registra-recorde-de-r-51-6-bilhoes

Na análise, o MCTI confirmou edição 2026 referente ao ano-base 2025, prazo publicado de 31/08/2026 e importações por planilhas em etapas específicas. Não extrapolar prazo ou layout para outros exercícios. O conteúdo integral da Portaria 9.563/2025 e os layouts de exportação não foram completamente auditados nesta conversa. Validar referências e vigência antes de codificar regras.

Controles contábeis e regularidade fiscal têm fundamento legal; hashes, classes A0–A4, tecnologias e revisão manual final são controles/políticas do produto. A regra geral de ausência de aprovação prévia não deve ser generalizada para todas as modalidades, em particular o art. 19-A. Não hardcodar condições fiscais universais sem base específica.

## Atualização futura

Registrar data, decisão, responsável, motivo, arquivos/contratos afetados e necessidade de revalidação. Uma IA pode sugerir melhoria, mas não assumir aprovação da equipe nem mudar silenciosamente o escopo de outra frente.

## Atualizações no repositório Basho

| Data | Decisão | Responsável | Motivo | Afetados | Revalidar |
|---|---|---|---|---|---|
| 2026-11-07 | Carlos assume **agente + dados** (antes: Vitor no mecanismo/núcleo, Thiago nos comportamentos). | Equipe | Redistribuição da frente para o hackathon | `roles/*.md` (divisão original preservada como histórico) | Vitor e Thiago confirmarem as novas fronteiras |
| 2026-11-07 | Sem LangGraph: orquestrador determinístico próprio com fila em Postgres; 4 responsabilidades viram perfis de tarefa do Maker. | Carlos | Manter ADR-0002/0004 e os contratos já mergeados | `ARQUITETURA.md` §Estrutura/§Agentes; ADR-0009 (proposta) | Aceite da ADR-0009 pela equipe |
| 2026-11-07 | Primeira entrega do agente = relatório individual do pesquisador (perfil `research_report`). | Carlos | É a base de consolidação, findings e ciclo de pendências | `EXECUCAO_E_ACEITE.md` §Sequência | — |

# ResearchOps — pacote de transferência para as IAs

Versão 1.0 · 07/11/2026 · Preparação do desenvolvimento para o Converge Challenge 2026.

Este pacote consolida os documentos e as correções posteriores de Thiago. Não contém código do produto e não implica que o repositório tenha sido inspecionado. Sua finalidade é fazer as cinco IAs trabalharem com o mesmo entendimento.

## Uso em cinco minutos

1. Envie o ZIP completo para Vitor e Carlos. Extraia-o também no ambiente de Thiago.
2. Preferencialmente, copie esta pasta para `docs/handoff/` do repositório compartilhado, preservando a documentação e as instruções existentes. Não substitua AGENTS.md ou CLAUDE.md sem antes conferir seu conteúdo.
3. Abra cada IA no repositório correto e use o prompt de ativação abaixo com seu arquivo de papel.
4. Na primeira interação, peça leitura e diagnóstico. Este pacote não autoriza iniciar automaticamente implementação, publicar, alterar permissões ou contatar terceiros.
5. Após integrar os documentos ao repositório, informe a todas as IAs o mesmo commit de referência. Atualizações posteriores devem ser registradas em DECISOES_E_LACUNAS.md.

## Prompt de ativação — copiar e preencher apenas o papel e o caminho

> Você participará do desenvolvimento do ResearchOps. Leia integralmente o pacote em [CAMINHO_DA_PASTA], começando por LEIA_PRIMEIRO.md, PRODUTO.md, ARQUITETURA.md, CONTRATOS.md, EXECUCAO_E_ACEITE.md e DECISOES_E_LACUNAS.md. Depois leia seu papel: roles/[ARQUIVO_DO_PAPEL].md. Os documentos em references/ são históricos: as correções explícitas do produto em PRODUTO.md refletem as decisões posteriores do usuário. Respeite também as instruções aplicáveis do repositório. Primeiro inspecione o código existente, sem editar, e devolva: entendimento do produto, responsabilidade atribuída, recursos existentes reutilizáveis, dependências, conflitos concretos e proposta da primeira entrega. Não reinicie brainstorming, não reduza o produto apenas à Lei do Bem e não redesenhe contratos compartilhados isoladamente. Não implemente nesta primeira resposta; aguarde a instrução de execução do responsável humano. Se algum arquivo não puder ser lido, informe qual em vez de presumir seu conteúdo.

## Quem recebe qual papel

| Pessoa | Ferramenta | Arquivo |
|---|---|---|
| Vitor | Codex | roles/VITOR_CODEX.md |
| Vitor | Claude Code | roles/VITOR_CLAUDE.md |
| Thiago | Claude Code | roles/THIAGO_CLAUDE.md |
| Thiago | Codex | roles/THIAGO_CODEX.md |
| Carlos | Claude Code | roles/CARLOS_CLAUDE.md |

Todos recebem a pasta completa, não apenas o arquivo individual. Os papéis são instruções para executores de desenvolvimento, não agentes que funcionarão dentro do produto.

## Leitura e prioridade

- Decisões explícitas posteriores dos responsáveis humanos prevalecem sobre este snapshot; registrar alterações compartilhadas.
- PRODUTO.md: visão atual confirmada e correções de escopo.
- ARQUITETURA.md: base técnica proposta nesta conversa; verificar compatibilidade com o repositório antes de implementar.
- CONTRATOS.md: proposta inicial de interfaces para ratificação técnica de Vitor, não contrato já implementado.
- EXECUCAO_E_ACEITE.md: sequência, colaboração, cenário e resultados esperados.
- DECISOES_E_LACUNAS.md: o que está confirmado, proposto e pendente.
- references/: textos originais, úteis para detalhes e histórico; não restaurar decisões superadas.

## Sem acesso a arquivos locais?

Anexe os Markdown comuns e o arquivo de papel à conversa da IA. Se a ferramenta não ler ZIP, extraia primeiro. Os arquivos podem ser lidos como texto comum. Não é necessário transmitir todo o histórico do ChatGPT.

## O que ainda não sabemos

URL e estado do repositório; prazo e regras integrais do evento; provedor/modelo da aplicação; acesso autorizado às integrações; orçamento e deploy. Essas informações não foram inventadas neste pacote. Apenas implementação dependente delas deve aguardar sua definição; análise e preparação independentes podem avançar.

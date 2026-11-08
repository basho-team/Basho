# Base arquitetural proposta

Status: recomendação preparada no ChatGPT e aceita como base para distribuição; repositório ainda não inspecionado. Não migrar trabalho existente automaticamente. Vitor coordena contratos, backend e integração; ChatGPT prepara a arquitetura e a especificação comum. Mudanças relevantes devem ser justificadas e compartilhadas com a equipe.

## Estrutura

Monorepositório, aplicação modular. React/TypeScript no frontend; FastAPI/Pydantic no backend; PostgreSQL para dados e estado persistente; arquivos fora das tabelas, com referências e versões; processo worker separado da API; LangGraph para execução dos agentes e pausa/retomada. As versões de dependências devem ser verificadas e fixadas no repositório, não inferidas deste documento.

Não introduzir por padrão microsserviços, banco de grafos, banco vetorial, Redis ou múltiplos frameworks de agentes. Relações explícitas no PostgreSQL bastam inicialmente. Adotar componentes adicionais apenas por necessidade concreta. Escolha do modelo/provedor da aplicação continua aberta.

## Módulos lógicos e proprietários

| Módulo | Função | Executor |
|---|---|---|
| core / api / storage | Entidades, persistência, autorização e contratos | Vitor Codex |
| reviews / releases | Revisões versionadas, encaminhamentos, snapshots | Vitor Codex |
| connectors / workflows / worker | Coleta, ferramentas externas, filas e retomadas | Vitor Claude |
| research / management | Relatórios individuais, consolidação e interpretação técnica | Thiago Claude |
| fiscal / reconciliation / exporters | Critérios, cálculos, sinalizações e pacote documental | Thiago Codex |
| frontend | Interfaces e integração das três experiências | Carlos Claude |

Nomes de diretórios são sugestão, sujeitos à estrutura existente. Uma migração de banco compartilhada deve ter responsável explícito. Outros executores propõem alterações de schema a Vitor, sem criar modelos paralelos.

## Agentes do produto

1. Documentação de pesquisa: organiza atividade e gera relatório fundamentado.
2. Coordenação: consolida, acompanha marcos e interpreta lacunas gerenciais.
3. Análise técnico-fiscal: interpreta critérios e propõe sinalizações, com ferramentas de cálculo e regras.
4. Investigação de pendências: busca informação, prepara ação autorizada e processa respostas.

São responsabilidades lógicas. Podem compartilhar funções e execução; não precisam de quatro serviços ou modelos diferentes. Vitor implementa o mecanismo e as ferramentas, Thiago implementa os comportamentos de domínio. O investigador pode ser reutilizado pelos três fluxos. O frontend não chama modelos ou ferramentas com credenciais diretamente.

## Fronteira IA/regras

IA: interpretar fontes, propor relações, investigar, resumir, redigir, explicar sinalizações e selecionar próximos passos permitidos.
Código: somas com precisão decimal, formatos, deduplicação, transições válidas, autorização, controle de acesso, versão aprovada, validação de schema, idempotência e gates de liberação.

O motor de regras não deve depender da confiança declarada pelo modelo para liberar um pacote. Uma referência existente é necessária, mas a correspondência entre fonte e afirmação também deve ser avaliada.

## Estado e revisão

Separar três estados: revisão documental; conciliação da despesa; avaliação do critério. Não propagar aprovação automaticamente entre eles.

Fonte atualizada cria nova versão. Artefatos dependentes são sinalizados como desatualizados e reavaliados. Aprovações anteriores continuam no histórico; novas versões materiais requerem revisão. Definir materialidade com critérios explícitos; na dúvida, revisão. Não alterar silenciosamente uma versão aprovada ou enviada.

LangGraph conserva o estado da execução; banco de domínio conserva a situação de negócio. Vitor deve definir uma única autoridade para cada campo, evitando dois estados divergentes. Pausar uma revisão não mantém um request HTTP ou uma chamada ao modelo aberta.

## Ferramentas externas

Primeira entrega: GitHub leitura, uploads autorizados e Notion leitura/escrita em escopo designado. Drive segue o mesmo contrato de ingestão e entra após o primeiro fluxo integrado. Não fazer suporte a três conectores atrasar o ciclo principal.

Registrar ação pretendida, chave idempotente, resultado e ID externo. Em timeout depois de uma possível criação externa, reconciliar o resultado antes de repetir. Não prometer exatamente uma execução somente porque existe uma chave local. Edição/fechamento manual de tarefa externa não comprova resolução da pendência por si só.

## Segurança mínima coerente com a demo

Permissões por pessoa/papel/projeto; escopo de empresa em consultas, arquivos, jobs e ferramentas. Nenhum segredo em prompt, frontend, log ou commit. Originais preservados; arquivos e texto de documentos são dados não confiáveis, inclusive tentativas de prompt injection. Dados pessoais minimizados. Configurações de modelo e acesso aprovadas pela equipe.

Se a demo alternar papéis sem autenticação real, isso deve ser identificado como mecanismo de demonstração, não segurança implementada. Não declarar suporte multiempresa pronto sem isolamento verificado. Hash verifica integridade desde a captura, não autenticidade legal da origem.

## Referências técnicas

- FastAPI: https://fastapi.tiangolo.com/features/
- LangGraph (documentação oficial): https://docs.langchain.com/oss/python/langgraph/interrupts
- Estado e retomada exigem testes de efeitos externos repetidos; não assumir que o framework garante todas as propriedades da aplicação.

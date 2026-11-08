# ADR-0009: Demonstração local com serviços determinísticos

- **Status:** proposta — implementação demonstrativa solicitada; arquitetura de produção preservada
- **Data:** 2026-11-08
- **Decisores:** equipe Basho — revisão pendente

## Contexto e problema

A etapa atual solicita interface funcional no Next.js existente, com Drive, Notion e GitHub fictícios, workflows determinísticos e persistência local. Não autoriza agentes, credenciais, serviços externos ou backend novo. As ADRs aceitas descrevem a arquitetura de produção; a ADR-0008 ainda é proposta.

## Opções consideradas

1. Construir backend e conectores reais agora.
2. Adicionar dados independentes por tela, sem alterações entre módulos.
3. Implementar uma camada única de simulação com comandos serializáveis e serviços desacoplados dos componentes.

## Decisão desta demonstração

Opção 3. O código em `frontend/src/services` contém exclusivamente regras de demonstração, sem assumir que substitui o backend alvo da ADR-0001. `OperationsAdapter` e `SimulationCommand` formam a fronteira para posterior substituição por chamadas autenticadas ao backend. Nenhuma ADR aceita é revogada por esta entrega.

O estado é uma organização fictícia por perfil do navegador. Projetos, documentos, atividades, eventos, evidências, execuções, aprovações e auditoria usam IDs e referências compartilhados. O armazenamento possui envelope versionado, recuperação explícita de erro e restauração de demonstração.

A execução guarda plano e cursor. Cada etapa valida a política atual, conexão, escopo e invariantes antes de alterar o estado. Aprovações autorizam o comando exato e não superam um bloqueio posterior. Uma etapa já concluída não é repetida após recarga. Eventos simultâneos acrescentam vínculos de evidências sem substituir os anteriores.

Evidências e auditoria recebem apenas acréscimos via serviços. Originais não são renomeados, movidos ou sobrescritos; cópias mantêm a origem. A restauração é uma operação explícita que substitui o cenário inteiro.

## Consequências

- **Positivas:** demonstração completa sem dependências novas, alterações externas ou credenciais; motor testável sem React e fluxos observáveis na interface.
- **Limitações:** localStorage não é banco, autenticação, RLS, ledger inviolável ou colaboração multiusuário. A auditoria local é demonstrativa e pode ser alterada pelas ferramentas do navegador. O orquestrador só avança com a aplicação aberta.
- **Produção:** autorização, transações, isolamento de tenant, idempotência de conectores, locks, cofre de segredos e ledger devem ser implementados no backend conforme ADRs aceitas. Maker–Checker e integrações reais continuam fora desta etapa.
- **Limite regulatório:** completude é presença de informação/documento; decisões de aprovação são operacionais. Não existe enquadramento, conciliação fiscal, formulário definitivo ou submissão oficial.

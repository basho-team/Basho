# ADR-0008: Autonomia documental e preparação do FORMP&D por exceção

- **Status:** proposta
- **Data:** 2026-11-07
- **Decisores:** equipe Basho — revisão e aceitação pendentes
- **Escopo:** propõe revisão parcial das ADRs 0001, 0003, 0004, 0005 e 0007; preserva 0002 e 0006

## Contexto e problema

O Manual regulatório de autonomia — Lei do Bem, v1.0, novembro/2026, fornecido para orientar a arquitetura, exige coleta em GitHub, Notion e Drive, execução por estados e intervenção humana por exceção material. A arquitetura anterior restringe o MVP ao GitHub, exige aprovação humana de todo artefato verificado e não separa processamento de documento, sustentação de afirmações e liberação anual. É necessário explicitar a mudança sem reescrever retroativamente decisões aceitas ou afirmar implementação existente.

## Opções consideradas

1. Manter o MVP GitHub e as aprovações universais, deixando o manual como evolução futura.
2. Trocar toda a stack e adotar conversas livres entre agentes especializados.
3. Preservar monólito, stack, ledger e verificação independente; adotar orquestrador determinístico, especializações restritas e autonomia por exceção, conforme o manual.

## Decisão proposta

Opção 3, detalhada em [arquitetura.md](../arquitetura.md).

- **ADR-0001:** manter módulos e serviços públicos; acrescentar workflows, versionamento, object store e exportadores dentro dos módulos existentes.
- **ADR-0003:** preservar ledger append-only e eventos de correção. Separar o estado do pipeline, o status supported/pending/disputed e as decisões humanas. Artefatos documentais verificados podem ser publicados autonomamente; approved/rejected fica reservado a decisões que demandam responsável. Snapshots fechados não são sobrescritos.
- **ADR-0004:** adotar agentes documental, técnico, financeiro e conformidade, coordenados por estados persistentes e contratos tipados. Preservar Maker/Checker independente nos artefatos formais e não expor raciocínio do Maker ao Checker. Falhas recuperáveis voltam para investigação limitada; divergências materiais persistentes geram exceção, em vez de encaminhar toda discordância diretamente ao humano.
- **ADR-0005:** manter níveis read/write_internal/external/formal aplicados em código. Permitir ações externas rotineiras somente em ações/destinos previamente autorizados pelo tenant, incluindo criação e sincronização de tarefas Notion. O agente não recebe ferramentas formal. Aprovações materiais internas têm endpoints humanos; transmissão e retificação oficiais ocorrem externamente, sem automação no MVP.
- **ADR-0007:** ampliar P0 para GitHub, Notion e Drive, proveniência, relatórios, ciclo real de exceção Notion e pacote para gestão. Conciliação financeira e mudança incremental são P1; ERP/escrituração e eventual integração com portal ficam em backlog sujeito a decisão futura.
- **ADRs 0002/0006:** preservar stack e segurança, ampliando seu alcance aos novos fluxos e ao armazenamento de arquivos.

Autonomia não autoriza inferir horas de commits, inventar comprovantes, decidir rateio controverso ou declarar elegibilidade definitiva. Gates de release são verificações determinísticas; não dependem de um texto persuasivo do modelo.

## Consequências

- **Positivas:** aderência ao manual, redução de aprovações de rotina, rastreabilidade por ano-base e tratamento localizado de exceções.
- **Negativas / custos:** três conectores, credenciais e escopos por tenant, store versionado, contratos de execução, conciliação, regras de liberação e maior esforço de testes. O escopo de demonstração é maior que o da ADR-0007 original.
- **Regras derivadas:** antes da implementação, compatibilizar contratos de branches paralelas, atualizar as regras do CLAUDE.md após a aceitação e implementar/testar T01–T11. Nenhuma mudança de runtime é entregue por esta ADR.
- **Transição:** esta ADR não presume aprovação da equipe. Até ser aceita, as ADRs anteriores continuam normativas para a implementação; a arquitetura descreve o alvo proposto. Após aceitação, registrar a substituição parcial segundo o processo do projeto e alinhar instruções e contratos no mesmo trabalho de implementação.

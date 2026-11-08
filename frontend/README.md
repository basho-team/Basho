# Basho · demonstração de gestão de PD&I

Interface funcional em Next.js 16.4.5, React 19, TypeScript strict, Tailwind e shadcn/ui. Preserva as rotas `/` e `/projetos` e acrescenta os módulos já previstos na navegação.

Tudo usa dados sintéticos no navegador. Não há OAuth, backend novo, chamadas a Drive/Notion/GitHub, LLM, agente real ou submissão oficial. As fontes do sistema são as entidades em `src/data/seedData.ts`; nenhuma informação de conta conectada ao assistente é utilizada.

## Executar

Requer Node.js 20.9+ e npm. Na raiz do repositório:

```powershell
cd frontend
npm ci
npm run dev
```

Abra http://localhost:3000. Não é necessário configurar `.env` ou credenciais. As fontes tipográficas usam a pilha local para que o build não dependa de downloads do Google Fonts.

Para produção local:

```powershell
npm run build
npm run start
```

## Preparar a demonstração

1. Abra **Integrações** e clique em **Simular conexão** no Drive e Notion e em **Instalar App simulada** no GitHub.
2. As conexões iniciam com pastas, base e repositórios fictícios selecionados. Em **Configurar**, altere o escopo e clique em **Salvar alterações**. A seleção de diretórios inclui subpastas. O link do Drive é apenas metadado; ele não importa pastas reais.
3. No Drive, a pasta de trabalho padrão pertence ao PD-001. Ao demonstrar outro projeto, selecione uma pasta compatível. Movimentações e cópias para pastas de outro projeto são bloqueadas.
4. Abra **Autonomia** para configurar políticas globais, por projeto ou por recurso. A regra mais específica prevalece; permissões de recurso usam o ID selecionado. Bloqueios formais não podem ser liberados. Acesso também depende da conexão e do escopo da integração.

## Demonstrar os workflows

**A — atualização técnica:** em **Central de Operações**, selecione PD-001 e clique em **Simular PR integrado**. A linha do tempo mostra a consulta ao GitHub, registro de evidência, atualização da atividade, vínculo da evidência e criação de relatório. Consulte os resultados em **Atividades**, **Documentos e evidências** e nos detalhes do projeto. Alternativamente, em **Integrações → GitHub**, clique em **Simular chegada** com **Pull request integrado** e um repositório monitorado. O evento inicia o fluxo se seu gatilho estiver habilitado.

**B — organização documental:** clique em **Simular documento**. Com a opção de original protegido marcada, o arquivo recebido permanece intacto e uma cópia de trabalho é criada na pasta configurada, com referência ao original. Desmarque a opção para demonstrar a movimentação de um derivado. A classificação usa metadados fictícios explícitos.

**C — decisão humana:** clique em **Simular exceção**. Uma atividade aberta sem evidências gera uma solicitação contextualizada. Em **Aprovações**, aprove a ação preparada para encaminhar a atividade para revisão; rejeite com justificativa para encerrar a execução; ou solicite ajustes, acrescente a complementação e reenvie para decisão. Aprovar esse encaminhamento não cria evidência, não encerra a pendência técnica e não valida elegibilidade.

Para demonstrar bloqueios, altere **Drive → Criar documentos** para **Bloqueado** e dispare A. O relatório não será criado. Retorne a política a **Automático** e use **Retomar após ajuste** na execução. Etapas concluídas não são repetidas. Com **Exige aprovação**, o fluxo pausa e só cria o documento depois da decisão individual; bloqueios posteriores continuam prevalecendo.

Todas as operações relevantes aparecem em **Histórico e auditoria**, com filtros por origem, execução, resultado e texto. Ações de configuração são decisões humanas; ações de dados passam pelo mesmo serviço de permissões usado pelos workflows.

## Outros módulos

- **Documentos:** árvore de diretórios, criação de pastas e arquivos, renomeação, movimentação, cópia, prévia, pesquisa global e filtros por projeto/categoria. Originais e pastas que os contêm são protegidos; não há exclusão automática.
- **Atividades:** Kanban e tabela; criação, edição, movimentação, conclusão, responsável, prazo, prioridade, origem, evidências e histórico. Conclusão exige aprovação por padrão. O botão de sincronização do Notion cria/atualiza uma atividade externa sintética estável.
- **Projetos:** contexto técnico, período, equipe, atividades, documentos financeiros, relatórios, evidências, fontes vinculadas, pendências e histórico em uma tela. As referências são recalculadas após as mudanças.
- **Lei do Bem:** checklist dos onze grupos documentais, vínculo a documentos e estados ausente/presente/em elaboração/pendente de revisão/validado. A completude conta itens presentes ou validados com documento do projeto; objetivos também podem ser atendidos pelo campo do projeto. Não é pontuação fiscal. A estrutura preliminar FORMP&D é um arquivo de apoio no Drive simulado, sem formulário definitivo ou transmissão.
- **Visão geral:** oito indicadores derivados do mesmo estado, atividade recente, execuções e pendências.

## Persistência e limites

O envelope `basho-demo-v2` no localStorage guarda configurações, planos, cursores, decisões e dados. Recarregar retoma execuções sem repetir etapas concluídas. O motor avança a cada 450 ms enquanto a aplicação está aberta. Falhas de leitura/escrita são informadas e o armazenamento inválido não é sobrescrito silenciosamente.

**Restaurar dados**, na barra superior, substitui todos os dados e configurações locais pelos dados iniciais após confirmação. Não afeta contas externas.

É uma demonstração para um navegador, não um sistema multiusuário. Políticas locais não substituem autorização no servidor; auditoria local não é inviolável, nem equivale ao ledger de produção. As ADRs de produção e a proposta [ADR-0009](../docs/adr/0009-demonstracao-local-deterministica.md) esclarecem a separação.

## Organização e extensão

| Caminho                              | Responsabilidade                                        |
| ------------------------------------ | ------------------------------------------------------- |
| `src/types/index.ts`                 | Entidades compartilhadas e comandos serializáveis       |
| `src/data/`                          | Dados sintéticos e políticas iniciais                   |
| `src/services/permissionService.ts`  | Resolução por escopo e acesso a recursos                |
| `src/services/simulationService.ts`  | Validações, mutações, referências e auditoria           |
| `src/services/workflowEngine.ts`     | Planos dos cenários, avanço, decisões e retomada        |
| `src/services/settingsService.ts`    | Configurações, projetos e vínculos de repositórios      |
| `src/services/persistenceService.ts` | Envelope versionado e validação de armazenamento        |
| `src/services/adapters.ts`           | Contrato `OperationsAdapter` e implementação simulada   |
| `src/store/demoStore.ts`             | Store observável, hidratação e agendamento local        |
| `src/components/modules/`            | Gerenciador de documentos, auditoria e visão do projeto |
| `src/app/`                           | Rotas preservadas e novos módulos                       |
| `tests/`                             | Testes de domínio e navegador sem dependência de IA     |

Futuras integrações devem substituir o adaptador por chamadas ao backend, mantendo contratos e IDs externos, com autorização, tenant, transações e idempotência verificadas no servidor. O plano serializável e os cursores permitem mover o agendamento para um worker. Não se deve conectar APIs reais diretamente às regras de permissão do navegador.

## Verificações

```powershell
npm run typecheck
npm test
npm run lint
npm run build
```

Os testes de serviço cobrem A/B/C, retomada após recarga, aprovações, rejeição, ajustes, bloqueios por escopo, conexões, proteção de originais, ciclos de pastas, consistência, concorrência, auditoria e recuperação de armazenamento.

Para testes de interface, mantenha `npm run start` em outro terminal e execute:

```powershell
npm run test:browser
```

O teste usa o Edge headless instalado no Windows, em perfil isolado, somente contra localhost. Não instala navegador ou acessa contas pessoais. É possível definir `BASHO_QA_BROWSER` para um executável Chromium compatível e `BASHO_QA_URL` para outra origem local. As capturas ficam em `.qa/`, ignorada pelo Git.

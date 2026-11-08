# Contratos mínimos — proposta para ratificação por Vitor

Estes contratos são um ponto de partida, não OpenAPI definitivo nem código existente. Vitor deve publicá-los no repositório antes que as frentes dependentes assumam formatos diferentes. Detalhes internos podem variar, preservando as invariantes abaixo.

## Objetos compartilhados

| Objeto | Informação mínima |
|---|---|
| Organization | ID, dados necessários da empresa, informações tributárias com fonte/status e política de acesso |
| User/ProjectMember | Identidade, papel e escopo de projeto; permissões verificadas no backend |
| Project | ID estável, organização, objetivo, responsáveis, requisitos e critérios de entrega |
| ReportingPeriod | Início/fim, fuso, periodicidade; distinto de ano-base fiscal e ano de envio |
| EvidenceVersion | ID, fonte, ID externo, revisão/hash, captura, autor quando disponível, acesso e localizador de trecho |
| Activity/Claim | Projeto, autor atribuído, período, afirmação, evidências, status e justificativa |
| ReportVersion | Tipo individual/gerencial/fiscal, projeto, período, versão, conteúdo estruturado, fontes e estado |
| Review | Revisor, papel, versão exata, decisão, correções, justificativa e data |
| Expense/Allocation | Documento, item, valor decimal, moeda, período, proposta de alocação, fundamento e estado de conciliação |
| Finding | Critério e versão, objeto analisado, sinalização, fontes, justificativa e lacunas |
| Exception | Motivo, objeto, responsável, evidência necessária, situação e tarefa externa associada |
| Action/Run | Correlação, ação autorizada, idempotência, tentativas, resultado e ID externo |
| Release | Versões incluídas, revisões, critérios avaliados, exclusões, pendências, manifesto e data |

Projeto permanece o mesmo ao longo dos anos. Visões fiscais são por projeto/ano-base. Relatório mensal não deve ser identificado apenas pelo ano-base.

## Estados e invariantes

- Afirmação: supported / pending / disputed. Supported exige suporte real à afirmação, não apenas um link.
- Revisão: draft / awaiting_researcher / awaiting_manager / available_to_fiscal; rótulos finais serão ratificados. Revisões são registros sobre versões, não um booleano genérico.
- Execução: queued / running / awaiting_input / completed / failed. Estado de execução não é estado de conformidade.
- Finding: supported_by_evidence / insufficient_information / possible_incompatibility / fiscal_judgment_required. Decisão humana tem registro separado.
- Pendência resolvida requer resposta/evidência e revalidação adequada, não apenas clique ou timeout.
- Despesa excluída permanece listada com motivo. Ausência de valor não vira zero.
- Somatório de alocações não pode ultrapassar valor atribuível do item. Não contar nota + pagamento + lançamento como três despesas.
- Controle de concorrência: revisão sobre versão antiga informa conflito, não aprova automaticamente a atual.
- Alteração material depois da revisão preserva o snapshot e marca dependentes para reavaliação.

## Interfaces entre os módulos

1. Ingestão recebe fontes autorizadas e retorna versões de evidência normalizadas; parsers e agentes não ganham acesso irrestrito ao computador.
2. Geração individual recebe projeto, pessoa, período e IDs de evidência; retorna relatório estruturado, referências e lacunas.
3. Consolidação recebe versões individuais e suas revisões; distingue conteúdo revisado de rascunho pendente.
4. Análise fiscal recebe atividades, evidências, despesas e regras aplicáveis versionadas; retorna findings e referências. Não modifica escrituração.
5. Ação externa recebe organização, alvo permitido, conteúdo, autor operacional e chave de idempotência; retorna estado confirmado/indeterminado/falha e referência externa.
6. Resolução recebe pendência, resposta/evidência e identidade de quem respondeu; dispara reprocessamento dos dependentes.
7. Exportação recebe snapshot selecionado; valida gates e produz pacote com inclusões/exclusões. Não envia ao portal oficial.

Todas as funções precisam de resultado estruturado. Narrativas são derivadas e não substituem IDs/estados. Erro deve indicar código, mensagem, correlação e possibilidade de retry, sem expor segredos. Vitor publica schemas e exemplos, permitindo que Carlos use respostas simuladas declaradas enquanto o backend fica pronto.

## API a detalhar

Operações necessárias: listar projetos; consultar fontes/evidências; disparar sincronização/fechamento; consultar execução; consultar/editar versão de relatório; registrar revisão; consultar consolidação; criar/resolver pendência; consultar despesas/findings; preparar/baixar pacote.

Rotas exatas e geração dos tipos TypeScript serão definidas por Vitor e Carlos. A UI usa IDs reais e não reproduz regras fiscais em componentes. Testes de contrato devem verificar compatibilidade dos exemplos usados pelo frontend com o schema real.

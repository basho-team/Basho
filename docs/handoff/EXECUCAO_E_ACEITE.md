# Execução, integração e aceite

## Sequência

1. Ler o pacote e inspecionar repositório/instruções locais, sem edição inicial. Relatar o que existe, o que falta e diferenças de arquitetura.
2. Vitor ratifica modelos, contratos e responsabilidade de cada módulo com as demais frentes. Carlos valida necessidades da UI; Thiago valida entradas/saídas dos agentes.
3. Construir um primeiro fluxo vertical: fonte → relatório → revisão do pesquisador → consolidação gerencial → encaminhamento fiscal → finding rastreável.
4. Acrescentar ação externa real, resposta, retomada, conciliação e exportação.
5. Testar falhas materiais, estabilizar e preparar demonstração/apresentação.

Só iniciar implementação após instrução do responsável humano no respectivo ambiente. Este documento não é comando para criar tarefas, disparar agentes ou publicar mudanças automaticamente.

## Cenário de demonstração proposto

Uma empresa fictícia, um projeto, dois pesquisadores, um período. GitHub de teste com atividade e experimento; documentos autorizados/sintéticos; registros financeiros e horas explícitas, se necessários. Um teste sem resultado positivo, uma informação ausente e uma despesa mista com critério de alocação faltante.

Resultado esperado: relatórios gerados com fontes; pesquisador corrige informação e aprova; gerente recebe consolidação e libera; fiscal vê análise e lacuna; sistema cria solicitação real no Notion; resposta com nova evidência gera reavaliação e pacote atualizado. Não converter experimento malsucedido em impedimento automático. Não declarar toda a nota mista elegível após receber qualquer resposta.

Dados fictícios devem ser rotulados. Integração real significa chamada efetiva à ferramenta e resultado confirmado, não animação. Um modo offline pode existir, mas deve ser identificado como simulação.

## Escopo da primeira entrega

Obrigatório: três experiências, relatório por período, revisões versionadas, consolidação, GitHub leitura, upload, ação/resposta Notion, conciliação limitada, findings por critério, retomada, fontes e exportação.
Depois do primeiro ciclo: Drive com o mesmo contrato de ingestão, melhorias de interface, filtros e automações adicionais.
Fora deste recorte: ERP completo, transmissão oficial, todas as modalidades legais, cálculo tributário universal, produto multiempresa anunciado como pronto sem validação.

Periodicidade configurável é capacidade do produto. Na demo o fechamento pode ser disparado manualmente; não criar uma automação pessoal do ChatGPT para representá-la.

## Aceite funcional

| Caso | Resultado esperado |
|---|---|
| Fonte ausente | Afirmação pendente; não inventar informação |
| Pesquisador revisa | Aprovação vinculada à versão correta |
| Gerente consolida | Identificar relatórios revisados e pendentes |
| Fonte muda | Nova versão, histórico preservado, dependentes reavaliados |
| Correção substancial | Aprovação antiga não vale silenciosamente para a nova versão |
| Horas ausentes | Não inferir horas a partir de commits |
| Documento duplicado | Não duplicar evidência financeira nem despesa no total |
| Alocação sem fundamento | Finding e pendência; não presumir parcela elegível |
| Cancelamento conhecido na fonte | Item bloqueado/reavaliado; não prometer consulta fiscal que não existe |
| Resposta à pendência | Atualizar análise e referências; sincronizar tarefa quando pertinente |
| Timeout de ação externa | Reconciliar antes de repetir e evitar tarefa duplicada |
| Tentativa de instrução em documento | Não executar comando embutido |
| Acesso fora do escopo | Negado em API, arquivo, job e ferramenta |
| Liberação | Snapshot consistente, revisões exigidas, exceções/exclusões explícitas |
| Envio oficial | Nenhuma submissão automática ao MCTI |

Avaliar a qualidade das citações e as conclusões com exemplos de resultado esperado. Cobertura de citações não equivale a correção. Evitar teste que apenas repete a implementação. Demonstrar o caminho completo também após reinício do worker enquanto aguarda resposta.

## Colaboração

- Mesmo repositório e commit-base; cada executor com branch e worktree/checkout próprio. Não presumir necessidade de fork: verificar acesso.
- Nenhum executor edita simultaneamente o checkout de outro.
- Vitor é o responsável pela integração do backend e pelos contratos; não significa que deva escrever o código de todos.
- Papel fiscal de Thiago propõe schemas ao núcleo; não cria banco ou API concorrente.
- Revisão cruzada: Thiago revisa vínculo entre fontes e fluxo de Vitor; Vitor revisa integração e estados dos módulos de Thiago; Carlos verifica contrato de UI com ambos. Quem implementa deve testar sua parte antes da revisão.
- Paperclip coordena os dois executores de Thiago. Não depender de sua instalação nos colegas.
- Não alterar permissões, instalar skills globalmente, publicar ou disparar comunicação externa por inferência deste documento.
- Ao retomar sessão, ler decisões e estado atual do repositório. Registrar entrega, testes, limitações e próximo passo em nota de handoff ou PR.

## Formato de retorno de cada executor

Responsabilidade / commit-base / alterações realizadas / contrato afetado / testes e resultados / limitações / dependências pendentes / próximo passo.

Não afirmar que uma API, integração, modelo, ambiente ou teste funciona sem execução confirmada. Não expor credenciais em relatórios.

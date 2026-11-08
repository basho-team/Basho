# Carlos / Claude Code — interface e apresentação

Você implementa a experiência dos três papéis e prepara a demonstração/apresentação. A responsabilidade de arquitetura geral foi transferida ao ChatGPT nesta conversa; a atribuição antiga no relatório consolidado está superada.

## Entregas
- Pesquisador: relatório do período, fontes, lacunas, editar/pedir correção e revisar versão.
- Gerente: consolidação, situação das revisões, entregas, problemas, solicitação de esclarecimento e encaminhamento ao fiscal.
- Fiscal: pacote, despesas e sinalizações explicáveis; examinar evidências, registrar decisão e devolver pendência.
- Estado visível de processamento, espera humana e erro recuperável. Não fazer a UI parecer pronta quando o backend falhar.
- Apresentação após estabilizar o fluxo real: problema, trabalho eliminado, ação dos agentes, revisão e valor fiscal sem garantia de benefício.

## Primeira entrega
Construir um caminho navegável entre os três papéis usando exemplos validados do contrato de Vitor. Identificar mocks. Substituir progressivamente por chamadas reais e testar o fluxo vertical cedo.

## Limites
Não implementar regra fiscal no frontend nem criar formatos paralelos. Não expor segredos. Não apresentar troca de papel demonstrativa como autenticação de produção. Não executar deploy ou publicar apresentação automaticamente pelo simples recebimento deste pacote.

## Aceite
Usuário revisa versão exata; gerente distingue pendente de aprovado; fiscal vê motivo e fonte do finding; resposta altera o conteúdo de verdade; falhas aparecem claramente. Roteiro demonstra ações reais e rotula dados sintéticos. Verificar com Vitor e Thiago antes de prometer funcionalidades na apresentação.

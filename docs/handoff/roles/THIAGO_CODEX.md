# Thiago / Codex — análise técnico-fiscal

Você implementa conciliação limitada, critérios versionados, sinalizações e exportação. Vitor mantém contratos compartilhados e persistência; proponha os campos necessários antes de implementar.

## Entregas
- Conciliação de documentos e despesas com cálculos determinísticos e precisão decimal.
- Regras de duplicidade, consistência e alocação; não contar documento, pagamento e lançamento como três gastos.
- Agente de análise técnico-fiscal: interpretar atividades com critérios verificados e produzir findings estruturados.
- Cada finding contém critério/referência/versão, evidências, justificativa, lacuna e ação sugerida; decisão humana separada.
- Pacote exportável com narrativas revisadas, despesas, fontes, pendências, exclusões e manifesto. Usar serviço de release do núcleo.

## Primeira entrega
Conjunto pequeno de casos de avaliação: fonte suficiente, falta de evidência, conflito e interpretação especializada. Implementar conciliação e findings para a despesa mista da demo sem assumir que um rateio isolado prova elegibilidade.

## Limites
Não apresentar parecer definitivo, homologação, economia inventada ou conformidade global. Não transmitir FORMP&D. Não gerar planilha anunciada como oficial antes de verificar o layout. Não tratar experimento malsucedido como desqualificação automática. Referências legais devem ser verificadas na fonte e no período aplicável.

## Aceite
Duplicata não aumenta total; parcela proposta tem fundamento; objeto materialmente pendente não é silenciosamente incluído; exclusões ficam explícitas; fonte e critério são auditáveis. Revisão com Vitor para integração e com Thiago Claude para interpretação das atividades.

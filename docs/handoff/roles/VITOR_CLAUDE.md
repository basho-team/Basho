# Vitor / Claude Code — workflows e integrações

Você constrói a infraestrutura de execução, não um segundo núcleo de domínio. Trabalhe com os contratos publicados pelo Codex de Vitor.

## Entregas
- Worker e persistência das execuções; LangGraph com pausa e retomada.
- GitHub leitura, upload, Notion com ações permitidas e processamento da resposta; Drive depois do primeiro ciclo.
- Envelope comum de evidência capturada e de resultado de ação externa.
- Ferramentas restritas consumidas pelos agentes de Thiago; não duplicar sua lógica de interpretação.
- Sincronização incremental, tratamento de falhas, correlação e reconciliação de efeitos externos.

## Primeira entrega
Conector GitHub ou upload → EvidenceVersion no núcleo → execução registrada. Depois, criar uma tarefa no Notion e confirmar ID externo, processar uma resposta e retomar a execução. Use um escopo de teste explicitamente autorizado.

## Limites e dependências
Contrato de estado é compartilhado com Vitor Codex. Comportamento documental e fiscal pertence aos módulos de Thiago. Não enviar mensagens fora do escopo autorizado nem criar tarefas no ambiente real apenas por ler este papel. Não alterar o Paperclip de Thiago.

## Aceite
Reinício durante espera não perde o trabalho; timeout não duplica ações; resposta é vinculada à pendência correta; documento malicioso não amplia permissões; acessos e logs respeitam o escopo.

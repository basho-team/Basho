# Basho — frontend

Next.js (App Router), TypeScript strict, Tailwind, TanStack Query e Zod.
Veja o [README da raiz](../README.md) para o backend.

## Demonstração local com login

No PowerShell, dentro de `frontend`:

```powershell
npm ci
$env:BASHO_DEMO_PASSWORD = 'escolha-uma-senha-local'
node scripts/configure-demo-login.mjs
Remove-Item Env:BASHO_DEMO_PASSWORD
npm run dev -- -p 3002 --hostname 127.0.0.1
```

Abra http://localhost:3002/login. O script preserva configurações existentes e recusa sobrescrever um login já configurado. O hash fica em `.env.local`, ignorado pelo Git. Use `NEXT_PUBLIC_DATA_SOURCE=mock` (padrão). A senha é compartilhada apenas entre as contas fictícias desta demonstração.

| Conta | Função | Acesso |
| --- | --- | --- |
| ana@lumen.example | Pesquisador | Relatórios, revisões, fontes e pendências próprios |
| bruno@lumen.example | Pesquisador | Relatórios, revisões, fontes e pendências próprios |
| marina@lumen.example | Gerente | Equipe, consolidação, fechamento e configuração das prévias |
| rafael@lumen.example | Fiscal | Pacote fiscal, sinalizações e documentos |

A função selecionada deve corresponder à conta. Alterar rota, header ou corpo não concede outra função. Sessões duram quatro horas; sair revoga o token no servidor. Os registros de sessão ficam em `.local-demo/sessions`, ignorado pelo Git. Os dados fictícios são compartilhados pelo processo local e voltam ao estado inicial após reiniciar o servidor.

## Fontes e integrações

A página `/integracoes` oferece prévias sintéticas dos três provedores para todas as contas. Pesquisadores veem somente suas fontes; apenas o gerente ativa, desativa e atualiza as prévias.

| Provedor | Situação real nesta revisão |
| --- | --- |
| GitHub | Conector no backend, condicionado a token e repositório configurados; testes com HTTP simulado |
| Notion | Fixture/prévia sintética; conector externo não implementado |
| Google Drive | Prévia sintética; conector externo não implementado |

“Verificar leitura” testa os dados locais e as permissões da conta. Não testa OAuth ou sincronização externa.

## API opcional

`NEXT_PUBLIC_DATA_SOURCE=api` exige o backend e as variáveis server-side da raiz. Além de `BASHO_DEMO_REVIEWERS`, configure `BASHO_DEMO_BACKEND_USERS` como JSON de accountId para UUID real autorizado (por exemplo, chaves `ana`, `bruno`, `marina`). Sem mapeamento a operação é recusada. A identidade vem da sessão; headers do navegador são ignorados.

Pendências e dossiê da API ficam restritos ao gerente, pois o contrato atual não distingue a pessoa designada. O fluxo fiscal continua sintético/indisponível na API. Este login não substitui SSO, membership ou autenticação de produção; consulte a [ADR-0011, proposta](../docs/adr/0011-login-local-demonstracao-por-funcao.md).

## Validação

```powershell
npm run lint
npm run typecheck
npm test
npm run build
# Com o servidor local em execução:
$env:BASHO_DEMO_TEST_PASSWORD = 'sua-senha-local'
node scripts/verify-demo-login.mjs
Remove-Item Env:BASHO_DEMO_TEST_PASSWORD
```

O teste HTTP cobre os quatro logins, CSRF, função indevida, links profundos, propriedade de relatórios, prévias, configuração e repetição de cookie após logout. `npm run gen:api` gera os tipos a partir do OpenAPI do backend.

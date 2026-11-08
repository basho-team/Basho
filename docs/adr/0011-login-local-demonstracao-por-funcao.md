# ADR-0011: Login local de demonstração com acesso por função

- **Status:** proposta — implementação local solicitada; revisão da equipe pendente
- **Data:** 2026-11-08
- **Decisores:** equipe Basho — aceite pendente
- **Escopo:** demonstração local; não substitui autenticação de produção da issue #47 nem as ADRs 0005 e 0006 aceitas

## Contexto e problema

O usuário solicitou uma página de login, escolha de função e funcionalidades limitadas, e escolheu explicitamente contas locais de demonstração. A interface anterior permitia assumir outro papel pela rota e outro pesquisador por botões. O BFF usava o papel declarado no navegador. Notion era apenas uma fixture e Drive não tinha conector na main 589e449.

## Opções consideradas

1. Só esconder menus e manter o papel escolhido no navegador.
2. Sessão local revogável e cadastro sintético autorizado, com verificações em páginas e APIs.
3. Implementar identidade organizacional real, SSO, membership e novos conectores nesta entrega.

## Decisão proposta

Implementar a opção 2 para a demonstração. As contas fictícias e seus papéis são fixos no servidor. A escolha de função no login deve corresponder à conta; não concede privilégio. A senha configurada localmente é verificada por scrypt. A sessão é um token opaco aleatório, com registro local no servidor, cookie HttpOnly/SameSite e expiração de quatro horas. Logout apaga o registro e revoga o token.

As rotas protegidas verificam a sessão. A demonstração usa operações allowlisted no servidor, schemas de entrada/saída e autorização por função e propriedade do relatório. Dados sintéticos são compartilhados somente entre as contas da organização fictícia e reiniciam com o processo do servidor.

As prévias de GitHub, Notion e Drive são sintéticas. Só o gerente configura/atualiza essas prévias; todos leem fontes permitidas à sua função, e pesquisadores somente fontes próprias. Verificar uma prévia não testa OAuth, credenciais, sincronização externa ou persistência no ledger.

O caminho opcional da API usa identidade de sessão com mapeamento explícito para usuário autorizado no backend; nenhum header/body do navegador concede identidade. O backend permanece com identity_verified:false. Ações fiscais permanecem sintéticas. A API de pendências ainda não vincula a pessoa designada; seu acesso por pesquisador fica indisponível nesse caminho até haver contrato compatível.

## Consequências

- O fluxo local é demonstrável com limites de acesso reais no servidor de demonstração.
- Não há cadastro de usuários reais, recuperação de senha, convite, membership organizacional persistente, SSO ou autenticação fiscal de produção.
- Sessões locais em arquivos e estado sintético em memória exigem um servidor local; não são solução distribuída ou de produção.
- Novos conectores reais para Notion/Drive continuam dependentes de contrato, configuração e decisão arquitetural; a ADR-0008 permanece proposta.
- Nenhuma aprovação fiscal ou elegibilidade é inferida. A revisão humana permanece vinculada à versão exata.

## Referências técnicas

- Next.js: guias locais de Authentication e Authentication with Cache Components da versão instalada.
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- [Node.js crypto](https://nodejs.org/api/crypto.html).

## Atualização (2026-11-08): entrada rápida opcional

Para a demonstração, `BASHO_DEMO_OPEN_ACCESS=true` habilita `POST /api/auth/demo`: um clique na conta
fictícia cria a sessão **sem senha**. É **desligada por padrão**, só aceita as contas do cadastro
sintético, mantém a checagem de origem, e a função continua vindo do cadastro (o cliente não escolhe).
Quem alcança o site entra com qualquer função, então vale só com dado sintético.

Com `BASHO_DEMO_SESSION_SECRET` (32+ caracteres) a sessão é um token assinado por HMAC, sem estado, para
ambiente serverless sem disco compartilhado. Troca-se a revogação no servidor por independência de
armazenamento: o logout apaga o cookie e o token vale até expirar (4 h). Sem o segredo, segue a sessão
em arquivo, revogável, do corte original.

# Handoff: login local por função

- Revisão base: main `589e449f42cba118c615015d259cf5e7406d667b`.
- Branch: `feat/47-login-funcoes-demo`.
- Decisão: [ADR-0011, proposta](../adr/0011-login-local-demonstracao-por-funcao.md); aprovação da equipe pendente.
- Escopo autorizado: contas locais sintéticas, acesso por função, prévias de fontes, temas e PR para revisão.
- Relacionada à #47; não encerra autenticação real dos endpoints formais.

## Contratos e consumidores

| Contrato | Produtor e consumidores | Mudança |
| --- | --- | --- |
| Sessão local | `frontend/src/lib/auth/session.ts`, proxy, layout e rotas auth/demo/integrations/BFF | Token opaco revogável; conta e função derivadas do cadastro sintético fixo |
| `identityFromRole(request, env, deps)` | `lib/server/bff-core.ts`; reports-bff e projects-bff | Agora assíncrono, usa sessão e mapeamento server-side para UUID autorizado; header do cliente não concede identidade |
| `identityFromPair(request, env, userId, role, deps)` | bff-core e reports-bff | Assíncrono; par do corpo deve corresponder à sessão |
| Operações sintéticas | `/api/demo`, demo-dispatch e demo-source | Schema allowlisted, autorização por função e propriedade por pesquisador |
| Prévias de fontes | `/api/integrations`, demo-integrations e IntegrationsView | Dados sintéticos para todos; configurar/atualizar somente gerente |
| Pendências e dossiê da API | projects-bff | Somente gerente até o contrato vincular pendência à pessoa designada |

Não há alterações de OpenAPI, migrações, ledger ou RLS. O backend continua com `identity_verified:false`. A prova de autorização deste patch é do servidor local de demonstração; não demonstra identidade organizacional real.

## Coordenação antes de merge

A consulta ao GitHub em 2026-11-08 encontrou:

- **PR #66**, `feat/publicacao-drive-notion`: altera bff-core, nav, .env.example e architecture; adiciona `lib/server/integrations-bff.ts` com chamada síncrona `identityFromRole(request, gate.env)`. Ao combinar, tornar `openSession` e seus consumidores assíncronos, passar `deps` e aguardar a identidade. Preservar suporte a DELETE e demais mudanças daquele PR. Manter distintas as prévias sintéticas deste PR e a publicação externa proposta no #66. A ADR de login foi numerada 0011 para não colidir com a ADR-0010 proposta no #66.
- **PR #67**, `chore/deploy-railway` (base `feat/14-seed-demo`): também cria `frontend/src/proxy.ts`, com Basic Auth de deploy no modo API e recusa de configuração ausente. É necessário compor os dois controles, preservando o fechamento do deploy e a autorização por sessão. Não substituir um pelo outro silenciosamente.
- **PR #65**, seed/launcher, não foi incorporado. Este patch se baseia diretamente na main acima.

A equipe responsável pelos PRs #66/#67 e o integrador dos contratos devem combinar a revisão e a ordem de integração. Este handoff não ratifica a ADR nem afirma compatibilidade com branches que ainda não foram combinadas. O PR de login permanece rascunho enquanto essa composição estiver pendente.

## Aceite da revisão combinada

1. Rodar lint, typecheck, testes e build do frontend na revisão combinada.
2. Sem credencial de deploy no modo API, manter a recusa esperada pelo #67; com ela, ainda exigir sessão individual.
3. Sem sessão, com sessão expirada/revogada, header de papel forjado ou acesso a relatório alheio, recusar a operação.
4. Pesquisador não pode configurar fontes nem alcançar os endpoints de links/publicações do gerente.
5. Revalidar as chamadas de BFF do #66 com identidade assíncrona e testar a origem exata no ambiente de proxy/deploy.
6. Testar os quatro perfis na demonstração; ligar conexões reais somente com configuração e contratos próprios.

## Evidência e limites

- 116 testes do frontend passaram, incluindo sessões, propriedade, spoofing, CSRF, limite de corpo e conflitos de versão.
- 58 testes existentes do conector GitHub/resiliência passaram com transporte simulado.
- Lint, typecheck e build passaram; navegador desktop/mobile cobriu login, temas, navegação por função, três prévias e logout.
- Revisão de segurança equivalente feita por subagente nativo independente. O comando `/security-review` não está disponível nesta instalação; não foi executado.
- Notion/Drive desta revisão são prévias locais. A implementação proposta no #66 não está incorporada e não foi validada por estes testes.
- Nenhuma chamada a Google/Notion/GitHub real, Maker/Checker com LLM, PostgreSQL ou RLS foi exercitada nesta entrega de frontend.

## Apresentação da interface

Por solicitação explícita do usuário, nomes e textos visíveis não exibem qualificadores como demonstração, sintético ou fictício. Metadados is_synthetic/isSynthetic e a documentação técnica continuam identificando a origem dos dados. Esta escolha de apresentação não implementa conexões externas nem altera as limitações acima.

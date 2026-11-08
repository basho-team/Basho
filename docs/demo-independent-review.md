# Revisão independente da demo Basho

Revisão de 08/11/2026, snapshot **46c4cd1**. Worktree de revisão: `Basho-wt-codex-review`, branch `feat/demo-independent-review`. A árvore e os dados da demo em `3765` não foram alterados por esta revisão.

O Claude avançou depois para `4552d29`/`ed5d094` (rascunho automático por regras e leitura primeiro). Esses commits **não** integram o snapshot funcionalmente testado aqui. Os patches precisam ser adaptados à UX nova e revalidados antes da apresentação dessa versão.

## Avaliação

A jornada persistida funciona na cópia corrigida em desktop e celular. O snapshot original tinha duas regressões importantes na interface: sucesso de confirmação e checks de uma versão apareciam associados à seguinte. Elas foram reproduzidas antes da correção. A análise fiscal permanece assistiva, com dois defeitos de backend não corrigidos nesta entrega.

| Verificação | Resultado observado |
| --- | --- |
| Inicialização com `scripts/demo/up.sh` | Passou em banco novo, container e portas próprios; migrações, seed, API e build padrão funcionaram na execução inicial |
| Confirmação v1 → correção v2 | Falhou no original: mensagem indevida de confirmação da v2; passou após correção |
| Checks v1 → correção v2 | Falhou no original: resultado v1 continuava visível; passou após isolar todo o estado por versão atual e o componente de checks por versão exibida |
| Conflito com outro cliente | Passou: 409 não grava; abrir versão atual refaz consultas e permite confirmar o ID indicado pelo backend |
| Cookie malformado `%` | Derrubava UI no original; após correção volta à seleção de persona, BFF responde normalmente |
| Navegação, erro/retry e largura de tela | Passaram em desktop e Pixel 7 |
| Versão/item/evidência/hash do dossiê | IDs resolvem na versão exata e hash corresponde ao evento consultado; interface corrigida abre referências completas e payload |
| Backend existente | ruff, format, mypy; **491 passed / 1 skipped** (LLM real) com Postgres próprio |
| Frontend corrigido | lint/typecheck e build webpack com Tailwind passaram |
| Roteiro CDP original (`frontend/tests/e2e-journey.mjs`) | Passou SEM alterar o script no banco novo: v1 → correção v2 → checks aprovados → horas formais/coordenação → v3 → Bia → gerente → fiscal; overflow móvel `false` |
| Playwright funcional | **20 passed** (dez cenários em duas configurações), mais oito verificações HTTP após fortalecer revisão humana/localizador; inclui HTTP e navegador, não vinte jornadas completas |
| Horas de outra pessoa | **Falha reproduzida e não corrigida**: referência de horas de Bia aceita no relatório de Ana sem lacuna de titularidade |
| Substituição além de 200 eventos | **Falha reproduzida e não corrigida**: fonte substituída volta a ser considerada válida quando a substituição sai da primeira página |

Os dois últimos casos são auditorias adversariais explícitas em `e2e/fiscal-limits.spec.mjs`. São falhas reais, excluídas da rodada verde de vinte casos; não foram removidas nem convertidas em sucesso esperado.

## Isolamento e comandos

Serviços de revisão: web `http://127.0.0.1:3885`, API `http://127.0.0.1:8885`, Postgres `127.0.0.1:55542`, container `basho-codex-review-pg`, volume `basho-codex-review-pgdata`. Segredos novos de teste ficam fora das árvores Git, nunca no navegador, relatório ou PR.

**Atenção ao inicializador do snapshot:** mudar `DEMO_PG_CONTAINER` não muda o volume fixo `basho-demo-pgdata`. Para esta revisão, o container foi previamente criado com volume exclusivo. Não usar o script com container novo apontando inadvertidamente ao volume da apresentação. O script também encerra processos nas portas configuradas: as portas da revisão foram conferidas livres antes de iniciar.

Depois de preparar o container exclusivo e o diretório privado de segredos de teste:

```sh
DEMO_SECRETS=/caminho/privado/de/teste DEMO_PG_CONTAINER=basho-codex-review-pg DEMO_PG_PORT=55542 DEMO_API_PORT=8885 DEMO_WEB_PORT=3885 DEMO_DB=basho_review_novo scripts/demo/up.sh
npm --prefix e2e ci
BASHO_BFF_URL=http://127.0.0.1:3885 BASHO_API_URL=http://127.0.0.1:8885 BASHO_E2E_MODE=api npm --prefix e2e test -- integrated-ui.spec.mjs integrated-journey.spec.mjs real-bff.spec.mjs real-api.spec.mjs version-conflict.spec.mjs
# Auditoria opt-in: os dois testes expõem defeitos conhecidos e devem falhar neste backend:
BASHO_BFF_URL=http://127.0.0.1:3885 BASHO_FISCAL_LIMITS=1 npm --prefix e2e test -- fiscal-limits.spec.mjs --project desktop
```

Para compilar onde o worker do Turbopack encontra EPERM:

```sh
BASHO_WEBPACK_BUILD=1 npm --prefix frontend run build -- --webpack
npm --prefix frontend run start -- --hostname 127.0.0.1 --port 3885
```

Esse fallback usa `@tailwindcss/postcss` 4.3.5 e mantém CSS real. Não executar rebuild sobre o mesmo `.next` enquanto o serviço estiver ativo. O build padrão passou na primeira inicialização; reconstruções posteriores falharam no worker do ambiente, inclusive na execução autorizada. Nenhuma configuração de segurança foi alterada.

## O que os testes provam

`integrated-journey` usa cliques para registrar atividade, associar evidência, criar v1, recarregar, executar checks com horas indevidas no texto, confirmar v1, corrigir v2, verificar que não herdou confirmação/checks, rejeitar revisão antiga, confirmar v2, aceitar como gerente e abrir o dossiê fiscal. A origem completa mostra versão/item, evidência e hash; o payload é consultado do backend.

Para não modificar o seed, somente a resposta `demo/context` é controlada nos testes de jornada/conflito: recebe projeto UUID exclusivo. Todas as outras rotas usam BFF/backend/Postgres reais. Isso não prova cadastro/seleção de projetos pelo usuário nem autenticação real. `real-bff` testa escrita HTTP, não cliques; `real-api` testa contratos HTTP. Os cenários não fazem chamadas a LLM.

## Limitações fiscais e de apresentação

- Fonte e hash identificam o registro citado; não provam veracidade do fato, pertinência do dispêndio ou elegibilidade. A interface não recomputa o hash: o compara ao hash registrado retornado pela API.
- O backend valida horas pelo tipo e projeto, sem assegurar titularidade/período aplicável. `EvidenceIn` não tem período formal estruturado. Coordenar com Vitor os campos, invariantes e consumidores; preservar a lacuna quando desconhecidos. Filtro visual sozinho não resolve o problema.
- A busca de substituições e a lista de evidências usam 200 eventos. A busca individual de IDs citados no dossiê existe, mas o mapa de substituições é incompleto. O detalhe fiscal corrigido informa quando o conteúdo não está na página; isso não corrige a classificação do backend nem prova ausência de substituição.
- O resumo estruturado do gerente ainda omite `uncertainties` e `result_claims` presentes na API/Markdown. Usar o texto exportável quando necessário e não alegar cobertura completa dessa visualização.
- Identidades e conteúdo são sintéticos; troca de persona não é autenticação. Confirmação de texto não valida horas/despesas nem decide enquadramento. LLM real e transmissão de FORMP&D não foram executados.
- O snapshot 46 não inclui conector GitHub; a main remota já avançou com #55/#54. Não confundir ausência no snapshot com ausência no repositório atual.

## Entregas e integração

Commits próprios locais sobre 46c4cd1:

- `07e1174`: testes e runner independentes, incluindo casos fiscais opt-in.
- `c3559cd`: confirmação/checks por versão, cookie inválido e recuperação de conflito.
- `44a7911`: origem completa no fiscal e tipos dos campos já existentes na API.
- `54cc002`: fallback webpack/Tailwind, equivalente ao propósito do antigo `9aa689f`; integrar um deles, sem duplicar.
- `5efb6ae`: correção complementar de chaves; a chave de Checks precisa do prefixo `checks:` para não colidir com a de CorrectionForm. A regressão foi ampliada para rodar checks novamente após confirmar v2; o roteiro CDP também cobre essa etapa. Não integrar apenas c3559cd sem 5efb6ae.

As entregas antigas de `feat/demo-frontend-validation` não foram incorporadas no snapshot. Seus testes foram adaptados; a interface mock #35 e o diagnóstico isolado não devem substituir a UI integrada. Fontes de sistema continuam opção para operação offline; não foram necessárias na primeira inicialização desta revisão.

A auditoria inicial encontrou onze commits não publicados da integração: `451c27f`, `66d3e34`, `889a400`, `751cb64`, `3f7ff96`, `9e939c1`, `6376f26`, `7601d19`, `7ffd9b1`, `34f672b`, `46c4cd1`. Antes do push, novo `git fetch origin` confirmou que todos já estavam publicados em `origin/feat/demo-integration` (PR #58). A restrição de publicar história privada deixou de existir. A branch de correções é referência sobre o snapshot 46; não substituir o fluxo novo nem integrar sua história inteira na main. O PR independente sobre a main contém apenas testes próprios e este relatório, e aponta para os commits de correção, sem duplicar o código do produto.

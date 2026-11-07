# ADR-0006: Segurança — RLS, LGPD, prompt injection e segredos

- **Status:** aceita
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
O sistema guarda propriedade intelectual, dados financeiros e dados pessoais de colaboradores, e alimenta LLMs com conteúdo de fontes externas.

## Decisão
1. **Multi-tenant com RLS**: toda tabela de negócio tem `tenant_id`; políticas RLS no Postgres usando `current_setting('app.tenant_id')` definido por transação. A aplicação conecta com role sem `BYPASSRLS`.
2. **Menor privilégio**: roles distintos para migração, API e worker; o role da aplicação não pode alterar `evidence_events` nem `audit_log`.
3. **LGPD**: minimização (só dados necessários à comprovação); dados pessoais em tabelas separadas; não enviar dados pessoais desnecessários a LLMs; logs sem PII.
4. **Prompt injection**: conteúdo de conectores é envelopado e marcado como **dado não confiável**; nunca concatenado em instruções do sistema; tools sensíveis protegidas pela policy (ADR-0005), não pelo prompt; o Checker também sinaliza instruções suspeitas.
5. **Segredos**: apenas variáveis de ambiente; `.env` no `.gitignore`; `.env.example` sem valores; validação na inicialização (falha rápida se faltar).
6. **Bordas**: Pydantic no backend e Zod no frontend; mensagens de erro sem detalhes internos; CORS restrito; rate limit nos endpoints do agente.
7. **Dados de demo**: sintéticos e marcados como tal (`is_synthetic`).

## Consequências
- **Positivas:** isolamento entre clientes garantido no banco, não só na aplicação.
- **Negativas:** testes e migrações precisam configurar o tenant da sessão.
- **Regras derivadas:** todo PR que toque auth, banco, conectores ou LLM passa por `/security-review`; teste automatizado garante isolamento entre tenants.

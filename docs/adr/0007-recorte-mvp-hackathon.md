# ADR-0007: Recorte do MVP para o hackathon (< 24h)

- **Status:** aceita (item "outros conectores" alterado pela ADR-0010: Drive e Notion, só leitura)
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
A demo precisa mostrar o **produto integrado** (operação de P&D + conformidade da Lei do Bem) com trabalho real de agente, em menos de 24h.

## Decisão
Um fluxo ponta a ponta (cenários A/C da síntese), com dados sintéticos marcados:

1. Projeto seed com atividade de P&D e repositório GitHub de demo.
2. Agente lê PRs/commits e detecta experimento sem justificativa técnica / registro de atividade.
3. Maker rascunha o registro com evidências citadas → checks determinísticos → Checker valida → pendência criada para o responsável.
4. Usuário confirma ou corrige na UI → novo evento no ledger → dependentes reavaliados.
5. Tela de dossiê: histórico, fontes, estados e artefato pronto para revisão humana.

**Dentro:** conector GitHub (leitura + criação de issue com aprovação), ledger, Maker–Checker, policy de tools, UI de pendências/correção/dossiê, RLS com tenant fixo.

**Fora:** envio de FORMP&D, decisão de elegibilidade, outros conectores, autenticação completa (SSO), integração com ERP/RH/contabilidade, cálculo de benefício fiscal.

## Consequências
- **Positivas:** demo focada que mostra o diferencial (P&D + conformidade no mesmo fluxo).
- **Negativas:** várias capacidades ficam só no desenho.
- **Regras derivadas:** implementação mínima, porém sem atalhos que violem ADR-0003/0005/0006; itens "fora" viram issues de backlog, não código morto.

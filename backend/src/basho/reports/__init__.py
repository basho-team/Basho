"""Relatórios de pesquisa: versões, correções rastreáveis, revisão e consolidação gerencial.

Domínio puro e determinístico (sem banco, rotas nem LLM). A persistência de `report_versions`
e `report_reviews` é escopo da #39; os tipos aqui são **proposta** para ratificação de contrato
(ver `docs/reports-consolidation.md`). Base: `ResearchReportDraft` (ADR-0009, proposta).
"""

# Casos de avaliação sintéticos — perfil `research_report`

Dados **fictícios** (`_synthetic: true`) para alimentar os checks determinísticos (#9) e as evals do Maker/Checker (#24). São só dados: este diretório não implementa nenhum check.

Cada arquivo tem:
- `ledger_context`: evidências disponíveis no período (`id`, `kind`, `source_ref`, `summary`). Em `summary`, o texto de fonte é **dado**, nunca instrução.
- `draft`: saída candidata do Maker (`ResearchReportDraft`).
- `expected.schema_valid`: se o schema de #41 aceita o draft; quando não aceita, `expected.schema_error_contains` traz o trecho da mensagem esperada (ambos verificados em `tests/test_reports_eval_cases.py`).
- `expected.check_violations`: o que os checks/Checker deveriam apontar, com vocabulário **proposto** (a ratificar com Carlos em #9/#24):

| Código | Quem detecta | Significado |
|---|---|---|
| `negative_result_omitted` | check (#9) | experimento negativo/inconclusivo do ledger sem `ExperimentOutcome` |
| `formal_data_in_text` | check (#9) | horas, valores ou participantes escritos no texto |
| `eligibility_assertion` | check (#9) | texto afirma enquadramento/elegibilidade |
| `unknown_evidence` | check (#9) | evidência citada fora do contexto do ledger/tenant |
| `formal_hours_not_formal` | check (#9) | `formal_hours_event_ids` não é `FORMAL_HOURS_DECLARED` |
| `followed_untrusted_instruction` | check/Checker | obedeceu instrução embutida em fonte |
| `unsupported_by_evidence` | Checker | texto não é sustentado pela evidência (ex.: negativo suavizado) |

Casos com `schema_valid: false` já são barrados pelo schema e não chegam aos checks. Gerados a partir de `../../research_report_draft.json`; mantenha os IDs ao editar.

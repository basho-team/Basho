"""Conectores de fontes externas: GitHub (ADR-0007), Google Drive e Notion (ADR-0012).

Todo conteúdo lido é **dado não confiável** (ADR-0006): vira evento no ledger e só chega ao
modelo envelopado em `untrusted_data`. Os conectores só leem; a única ação externa é
`github_create_issue`, com aprovação humana (ADR-0005).
"""

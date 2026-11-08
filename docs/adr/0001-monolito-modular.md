# ADR-0001: Monólito modular

- **Status:** aceita
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
Equipe pequena, hackathon de < 24h e domínio ainda em descoberta (P&D + Lei do Bem). Precisamos de fronteiras claras sem custo operacional de sistemas distribuídos.

## Opções consideradas
1. Microsserviços por domínio
2. Monólito sem fronteiras
3. **Monólito modular** com módulos de domínio e interfaces explícitas

## Decisão
Opção 3. Um backend FastAPI com módulos (`projects`, `activities`, `evidence`, `people`, `expenses`, `compliance`, `agent`, `connectors`, `audit`). Um processo `api` e um processo `worker` a partir do mesmo código.

## Consequências
- **Positivas:** deploy único, transações locais, refatoração barata, extração futura possível.
- **Negativas:** exige disciplina para não acoplar módulos.
- **Regras derivadas:**
  - Módulo só chama outro módulo pelo seu `service` público; nunca importa `repository` ou modelos ORM de outro módulo.
  - Regra de negócio fica em `domain/`/`service.py`, não em rotas nem no frontend.
  - Arquivos < 800 linhas; funções < 50 linhas.

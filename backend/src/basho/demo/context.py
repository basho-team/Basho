"""Organização fictícia da demo. Pessoas e projeto são constantes sintéticas declaradas aqui
porque ainda não existe cadastro de projetos/pessoas (backlog); IDs fixos e reprodutíveis."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from basho.agent.artifacts import Periodicity, ReportingPeriod

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_NAME = "Detecção de falhas em motores (quantização embarcada)"
PERIOD = ReportingPeriod(
    start=date(2026, 10, 1),
    end=date(2026, 10, 31),
    timezone="America/Sao_Paulo",
    periodicity=Periodicity.MONTHLY,
)
FISCAL_YEAR = 2026


class Person(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    name: str
    role: str  # researcher | manager | fiscal


ANA = Person(
    id=UUID("33333333-3333-4333-8333-333333333333"), name="Ana (fictícia)", role="researcher"
)
BIA = Person(
    id=UUID("44444444-4444-4444-8444-444444444444"), name="Bia (fictícia)", role="researcher"
)
CARLA = Person(
    id=UUID("55555555-5555-4555-8555-555555555555"), name="Carla (fictícia)", role="manager"
)
DAVI = Person(
    id=UUID("66666666-6666-4666-8666-666666666666"), name="Davi (fictício)", role="fiscal"
)
PEOPLE = (ANA, BIA, CARLA, DAVI)


class DemoContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    is_synthetic: bool = True
    project_id: UUID = PROJECT_ID
    project_name: str = PROJECT_NAME
    period: ReportingPeriod = PERIOD
    fiscal_year: int = FISCAL_YEAR
    people: tuple[Person, ...] = PEOPLE
    ai_maker_available: bool = False
    ai_checker_available: bool = False
    ai_detail: str = (
        "Maker e Checker por LLM estão implementados (#8/#9), mas não há chave de API "
        "configurada neste ambiente e não haverá custo adicional: a demo usa checks "
        "determinísticos reais e relatórios montados pelo pesquisador."
    )

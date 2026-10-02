from enum import Enum
from uuid import UUID, uuid4
from pydantic import Field
from .base import DomainModel

class SearchEngineType(str, Enum):
    """Search engines available via SerpApi."""
    GOOGLE_SEARCH = "GOOGLE_SEARCH"
    GOOGLE_JOBS = "GOOGLE_JOBS"
    GOOGLE_NEWS = "GOOGLE_NEWS"
    GOOGLE_MAPS = "GOOGLE_MAPS"
    GOOGLE_FORUMS = "GOOGLE_FORUMS"
    GOOGLE_ADS = "GOOGLE_ADS"


class SearchTask(DomainModel):
    """A single search query to be executed on a specific engine."""
    task_id: UUID = Field(default_factory=uuid4)
    claim_id: UUID
    query: str
    engine: SearchEngineType
    rationale: str


class InvestigationPlan(DomainModel):
    """A plan for gathering evidence to verify claims."""
    plan_id: UUID = Field(default_factory=uuid4)
    claim_decomposition_id: UUID
    search_tasks: list[SearchTask] = Field(default_factory=list)
    total_engines_selected: int
    reasoning: str

from datetime import datetime
from uuid import UUID, uuid4
from pydantic import Field
from .base import DomainModel
from .claims import ClaimType
from .evidence import Evidence
from .investigation import SearchTask, SearchEngineType
from .findings import ClaimFinding, EvidenceGap, RiskIndicator

class InvestigationReport(DomainModel):
    """The final report summarizing the investigation of a claim."""
    report_id: UUID = Field(default_factory=uuid4)
    original_claim: str
    claim_type: ClaimType
    investigated_at: datetime
    claim_findings: list[ClaimFinding] = Field(default_factory=list)
    evidence_collection: list[Evidence] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    risk_indicators: list[RiskIndicator] = Field(default_factory=list)
    search_tasks_executed: list[SearchTask] = Field(default_factory=list)
    engines_used: list[SearchEngineType] = Field(default_factory=list)
    total_sources_found: int
    total_evidence_pieces: int
    limitations: list[str] = Field(default_factory=list)
    methodology_note: str

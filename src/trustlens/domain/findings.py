from enum import Enum
from typing import Literal, Optional
from uuid import UUID, uuid4
from pydantic import Field
from .base import DomainModel
from .investigation import SearchEngineType

class ClaimStatus(str, Enum):
    """The verified status of a claim based on evidence."""
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIED = "UNVERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    MIXED_EVIDENCE = "MIXED_EVIDENCE"


class EvidenceGap(DomainModel):
    """An area where sufficient evidence could not be found."""
    claim_id: UUID
    claim_text: str
    gap_description: str
    suggested_query: Optional[str] = None
    suggested_engine: Optional[SearchEngineType] = None


class RiskIndicator(DomainModel):
    """An indicator of potential risk, fraud, or red flags."""
    indicator_id: UUID = Field(default_factory=uuid4)
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    explanation: str


class ClaimFinding(DomainModel):
    """A summary of findings for a specific atomic claim."""
    claim_id: UUID
    claim_text: str
    status: ClaimStatus
    supporting_evidence: list[UUID] = Field(default_factory=list)
    contradicting_evidence: list[UUID] = Field(default_factory=list)
    neutral_evidence: list[UUID] = Field(default_factory=list)
    summary: str

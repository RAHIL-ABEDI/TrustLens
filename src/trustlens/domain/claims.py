from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from pydantic import Field
from .base import DomainModel

class ClaimType(str, Enum):
    """Types of claims being investigated."""
    JOB_OFFER = "JOB_OFFER"
    COMPANY_CLAIM = "COMPANY_CLAIM"
    PRODUCT_CLAIM = "PRODUCT_CLAIM"
    ONLINE_OFFER = "ONLINE_OFFER"
    GENERAL = "GENERAL"


class AtomicClaim(DomainModel):
    """A single, indivisible claim extracted from a larger text."""
    claim_id: UUID = Field(default_factory=uuid4)
    text: str = Field(..., min_length=3, max_length=2000)
    claim_type: ClaimType
    entities: list[str] = Field(default_factory=list)
    parent_claim_id: Optional[UUID] = None


class ClaimDecomposition(DomainModel):
    """The breakdown of an original claim into atomic claims."""
    decomposition_id: UUID = Field(default_factory=uuid4)
    original_claim: str = Field(..., min_length=3)
    claim_type: ClaimType
    atomic_claims: list[AtomicClaim] = Field(default_factory=list)
    rationale: str

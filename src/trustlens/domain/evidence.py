from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from pydantic import Field
from .base import DomainModel

class EvidenceStance(str, Enum):
    """The stance of the evidence relative to the claim."""
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    NEUTRAL = "NEUTRAL"
    IRRELEVANT = "IRRELEVANT"


class SourceType(str, Enum):
    """Type of the source document."""
    WEB_PAGE = "WEB_PAGE"
    NEWS_ARTICLE = "NEWS_ARTICLE"
    JOB_LISTING = "JOB_LISTING"
    BUSINESS_LISTING = "BUSINESS_LISTING"
    FORUM_POST = "FORUM_POST"
    OFFICIAL_SITE = "OFFICIAL_SITE"
    ADVERTISER_REGISTRY = "ADVERTISER_REGISTRY"
    UNKNOWN = "UNKNOWN"


class Source(DomainModel):
    """Information about the source where evidence was found."""
    source_id: UUID = Field(default_factory=uuid4)
    url: str
    hostname: str
    title: str
    source_type: SourceType
    publication_date: Optional[str] = None
    engagement_metadata: Optional[str] = None
    retrieved_at: datetime
    snippet: Optional[str] = None


class Evidence(DomainModel):
    """A specific piece of evidence extracted from a source."""
    evidence_id: UUID = Field(default_factory=uuid4)
    claim_id: UUID
    source: Source
    passage: str
    stance: EvidenceStance
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    search_engine: str
    search_query: str

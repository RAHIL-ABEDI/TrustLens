"""
Phase 4: Deterministic Outcome Testing
Fully offline, mocked LLM and SerpApi providers.
"""

import pytest
from unittest.mock import AsyncMock, patch

from trustlens.config.settings import TrustLensSettings
from trustlens.domain.claims import ClaimDecomposition, AtomicClaim, ClaimType
from trustlens.domain.evidence import EvidenceStance, SourceType
from trustlens.domain.investigation import InvestigationPlan, SearchTask, SearchEngineType
from trustlens.domain.findings import ClaimStatus
from trustlens.workflow.state import configure_providers
from trustlens.workflow.graph import create_investigation_workflow


class FakeGeminiProvider:
    def __init__(self, scenario: str):
        self.scenario = scenario

    async def analyze_claim(self, claim_text: str) -> ClaimDecomposition:
        if self.scenario == "CORRECT":
            return ClaimDecomposition(
                original_claim=claim_text,
                claim_type=ClaimType.ONLINE_OFFER,
                atomic_claims=[
                    AtomicClaim(text="SerpApi India Hackathon 2026 accepts solo participants", claim_type=ClaimType.ONLINE_OFFER),
                    AtomicClaim(text="SerpApi India Hackathon 2026 accepts teams of up to five members", claim_type=ClaimType.ONLINE_OFFER),
                ],
                rationale="Decomposed into participation rules."
            )
        elif self.scenario == "INCORRECT":
            return ClaimDecomposition(
                original_claim=claim_text,
                claim_type=ClaimType.GENERAL,
                atomic_claims=[
                    AtomicClaim(text="The SerpApi India Hackathon 2026 submission deadline is October 5, 2026", claim_type=ClaimType.GENERAL)
                ],
                rationale="Decomposed deadline claim."
            )
        elif self.scenario == "PARTLY_CORRECT":
            return ClaimDecomposition(
                original_claim=claim_text,
                claim_type=ClaimType.GENERAL,
                atomic_claims=[
                    AtomicClaim(text="The SerpApi India Hackathon 2026 submission deadline is October 5, 2026", claim_type=ClaimType.GENERAL),
                    AtomicClaim(text="The demo video must be under three minutes", claim_type=ClaimType.GENERAL),
                ],
                rationale="Decomposed deadline and demo claim."
            )
        elif self.scenario == "UNVERIFIED":
            return ClaimDecomposition(
                original_claim=claim_text,
                claim_type=ClaimType.GENERAL,
                atomic_claims=[
                    AtomicClaim(text="Every SerpApi India Hackathon 2026 participant receives a paid SerpApi internship", claim_type=ClaimType.GENERAL)
                ],
                rationale="Decomposed internship claim."
            )
        return ClaimDecomposition(original_claim=claim_text, claim_type=ClaimType.GENERAL, atomic_claims=[], rationale="")

    async def classify_evidence_stance(self, claim_text: str, passage: str) -> tuple[EvidenceStance, float, str, str | None, str | None]:
        if self.scenario == "CORRECT":
            if "solo participants" in claim_text:
                return (EvidenceStance.SUPPORTING, 1.0, "Supports solo", None, "accepts solo participants")
            if "teams of up to five" in claim_text:
                return (EvidenceStance.SUPPORTING, 1.0, "Supports team size", None, "teams of up to five members")
        elif self.scenario == "INCORRECT":
            if "October 5" in claim_text and "Oct 10, 2026" in passage:
                return (EvidenceStance.CONTRADICTING, 1.0, "Contradicts deadline", "The deadline is October 10, 2026", "Submit by Oct 10, 2026")
        elif self.scenario == "PARTLY_CORRECT":
            if "October 5" in claim_text and "Oct 10" in passage:
                return (EvidenceStance.CONTRADICTING, 1.0, "Contradicts deadline", "The deadline is October 10, 2026", "Submit by Oct 10, 2026")
            if "demo video" in claim_text and "under three minutes" in passage:
                return (EvidenceStance.SUPPORTING, 1.0, "Supports demo length", None, "demo video must be under three minutes")
        
        return (EvidenceStance.IRRELEVANT, 0.0, "No match", None, None)

    async def generate_investigation_plan(self, decomposition: ClaimDecomposition) -> InvestigationPlan:
        return InvestigationPlan(
            plan_id=decomposition.atomic_claims[0].claim_id if decomposition.atomic_claims else None,
            claim_decomposition_id=decomposition.decomposition_id,
            search_tasks=[
                SearchTask(
                    claim_id=ac.claim_id,
                    query=f"verify {ac.text}",
                    engine=SearchEngineType.GOOGLE_SEARCH,
                    rationale="search"
                ) for ac in decomposition.atomic_claims
            ],
            total_engines_selected=1,
            reasoning="Mocked plan"
        )

    async def analyze_risks(self, findings_json: str, evidence_json: str) -> dict:
        return {"risk_indicators": [], "limitations": []}

    async def _generate_json(self, prompt: str) -> dict:
        if "risk indicators" in prompt:
            return {"risk_indicators": [], "limitations": []}
        if "evidence gaps" in prompt:
            if self.scenario == "UNVERIFIED":
                return {
                    "gaps": [
                        {
                            "claim_index": 0,
                            "gap_description": "No evidence found to verify or refute this claim.",
                            "suggested_query": "internship program",
                            "suggested_engine": "GOOGLE_SEARCH"
                        }
                    ],
                    "needs_second_search": False
                }
            return {"gaps": [], "needs_second_search": False}
        return {}

    async def generate_report_summary(self, claim: str, findings: str) -> str:
        return "Mocked methodology"


class FakeSerpApiProvider:
    def __init__(self, *args, **kwargs):
        pass
    async def search(self, engine, query, **kwargs):
        return []


@pytest.fixture
def base_settings():
    return TrustLensSettings(
        serpapi_api_key="mock",
        gemini_api_key="mock",
        max_search_calls=5,
    )


def initial_state(claim: str):
    return {
        "original_claim": claim,
        "claim_type": "",
        "decomposition": {},
        "atomic_claims": [],
        "investigation_plan": {},
        "search_tasks": [],
        "raw_search_results": [],
        "search_calls_made": 0,
        "engines_used": [],
        "evidence_collection": [],
        "claim_findings": [],
        "evidence_gaps": [],
        "needs_second_search": False,
        "second_search_results": [],
        "second_search_evidence": [],
        "risk_indicators": [],
        "limitations": [],
        "report": {},
        "methodology_note": "",
        "current_step": "starting",
        "error": "",
    }


@pytest.mark.asyncio
@patch("trustlens.workflow.graph._fetch_url_text")
@patch("trustlens.workflow.state.GeminiProvider")
@patch("trustlens.workflow.state.SerpApiProvider")
async def test_scenario_correct(MockSerpApi, MockGemini, mock_fetch, base_settings):
    """Scenario 1: CORRECT"""
    MockGemini.return_value = FakeGeminiProvider("CORRECT")
    MockSerpApi.return_value = FakeSerpApiProvider()
    mock_fetch.return_value = "Official rules: accepts solo participants and teams of up to five members."
    
    claim = "SerpApi India Hackathon 2026 accepts solo participants and teams of up to five members. https://serpapi.github.io/"
    
    configure_providers(base_settings)
    workflow = create_investigation_workflow(base_settings)
    
    result = await workflow.ainvoke(initial_state(claim))
    report = result["report"]
    
    assert report["overall_status"] == "CORRECT"
    
    findings = report["claim_findings"]
    assert len(findings) == 2
    for f in findings:
        assert f["status"] == ClaimStatus.CORRECT
        assert "serpapi.github.io" in f["evidence_source_url"]
        assert f["correction"] is None
        assert f["evidence_excerpt"] is not None


@pytest.mark.asyncio
@patch("trustlens.workflow.graph._fetch_url_text")
@patch("trustlens.workflow.state.GeminiProvider")
@patch("trustlens.workflow.state.SerpApiProvider")
async def test_scenario_incorrect(MockSerpApi, MockGemini, mock_fetch, base_settings):
    """Scenario 2: INCORRECT"""
    MockGemini.return_value = FakeGeminiProvider("INCORRECT")
    MockSerpApi.return_value = FakeSerpApiProvider()
    mock_fetch.return_value = "Submit by Oct 10, 2026."
    
    claim = "The SerpApi India Hackathon 2026 submission deadline is October 5, 2026. https://serpapi.github.io/"
    
    configure_providers(base_settings)
    workflow = create_investigation_workflow(base_settings)
    
    result = await workflow.ainvoke(initial_state(claim))
    report = result["report"]
    
    assert report["overall_status"] == "INCORRECT"
    
    findings = report["claim_findings"]
    assert len(findings) == 1
    f = findings[0]
    assert f["status"] == ClaimStatus.INCORRECT
    assert f["correction"] == "The deadline is October 10, 2026"
    assert "Submit by Oct 10" in f["evidence_excerpt"]


@pytest.mark.asyncio
@patch("trustlens.workflow.graph._fetch_url_text")
@patch("trustlens.workflow.state.GeminiProvider")
@patch("trustlens.workflow.state.SerpApiProvider")
async def test_scenario_partly_correct(MockSerpApi, MockGemini, mock_fetch, base_settings):
    """Scenario 3: PARTLY_CORRECT"""
    MockGemini.return_value = FakeGeminiProvider("PARTLY_CORRECT")
    MockSerpApi.return_value = FakeSerpApiProvider()
    mock_fetch.return_value = "Submit by Oct 10, 2026. The demo video must be under three minutes."
    
    claim = "The SerpApi India Hackathon 2026 submission deadline is October 5, 2026 and the demo video must be under three minutes. https://serpapi.github.io/"
    
    configure_providers(base_settings)
    workflow = create_investigation_workflow(base_settings)
    
    result = await workflow.ainvoke(initial_state(claim))
    report = result["report"]
    
    assert report["overall_status"] == "PARTLY_CORRECT"
    
    findings = report["claim_findings"]
    assert len(findings) == 2
    
    f1 = next(f for f in findings if "October 5" in f["claim_text"])
    assert f1["status"] == ClaimStatus.INCORRECT
    assert f1["correction"] == "The deadline is October 10, 2026"
    
    f2 = next(f for f in findings if "demo video" in f["claim_text"])
    assert f2["status"] == ClaimStatus.CORRECT
    assert f2["correction"] is None
    assert "under three minutes" in f2["evidence_excerpt"]


@pytest.mark.asyncio
@patch("trustlens.workflow.graph._fetch_url_text")
@patch("trustlens.workflow.state.GeminiProvider")
@patch("trustlens.workflow.state.SerpApiProvider")
async def test_scenario_unverified(MockSerpApi, MockGemini, mock_fetch, base_settings):
    """Scenario 4: UNVERIFIED"""
    MockGemini.return_value = FakeGeminiProvider("UNVERIFIED")
    MockSerpApi.return_value = FakeSerpApiProvider()
    mock_fetch.return_value = "We host an annual hackathon. Welcome!"
    
    claim = "Every SerpApi India Hackathon 2026 participant receives a paid SerpApi internship. https://serpapi.github.io/"
    
    configure_providers(base_settings)
    workflow = create_investigation_workflow(base_settings)
    
    result = await workflow.ainvoke(initial_state(claim))
    report = result["report"]
    
    assert report["overall_status"] == "UNVERIFIED"
    
    findings = report["claim_findings"]
    assert len(findings) == 1
    f = findings[0]
    assert f["status"] == ClaimStatus.UNVERIFIED
    
    assert len(report["evidence_gaps"]) == 1
    assert "No evidence found" in report["evidence_gaps"][0]["gap_description"]

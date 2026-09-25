"""
TrustLens Workflow State + Provider Registry.

TypedDict state for LangGraph plus a module-level registry for
providers (LLM, SerpApi, settings) that nodes access without
passing non-serializable objects through graph state.
"""

from __future__ import annotations

from typing import Any, TypedDict

from trustlens.config.settings import TrustLensSettings
from trustlens.providers.llm import GeminiProvider
from trustlens.providers.serpapi import SerpApiProvider


class InvestigationState(TypedDict, total=False):
    """State flowing through the LangGraph investigation pipeline."""

    # Input
    original_claim: str
    claim_type: str

    # Claim Analysis
    decomposition: dict
    atomic_claims: list[dict]

    # Investigation Plan
    investigation_plan: dict
    search_tasks: list[dict]

    # Search Results
    raw_search_results: list[dict]
    search_calls_made: int
    engines_used: list[str]

    # Evidence
    evidence_collection: list[dict]
    claim_findings: list[dict]

    # Gap Detection
    evidence_gaps: list[dict]
    needs_second_search: bool

    # Targeted Search
    second_search_results: list[dict]
    second_search_evidence: list[dict]

    # Risk Analysis
    risk_indicators: list[dict]
    limitations: list[str]

    # Report
    report: dict
    methodology_note: str

    # Control
    current_step: str
    error: str


# ── Provider Registry ───────────────────────────────────────────────
# Nodes access providers via this module-level registry instead of
# passing non-serializable objects through LangGraph state channels.

class _ProviderRegistry:
    """Holds references to provider instances for the current run."""

    settings: TrustLensSettings | None = None
    llm: GeminiProvider | None = None
    serpapi: SerpApiProvider | None = None
    progress_callback: Any = None  # Optional Streamlit callback


registry = _ProviderRegistry()


def configure_providers(
    settings: TrustLensSettings,
    *,
    progress_callback: Any = None,
) -> None:
    """Configure the provider registry before running a workflow.

    Args:
        settings: Application settings with API keys.
        progress_callback: Optional callable(step_name, detail) for UI updates.
    """
    registry.settings = settings
    registry.llm = GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )
    registry.serpapi = SerpApiProvider(
        api_key=settings.serpapi_api_key,
        timeout_seconds=settings.search_timeout_seconds,
    )
    registry.progress_callback = progress_callback


def _progress(step: str, detail: str = "") -> None:
    """Report progress if a callback is configured."""
    if registry.progress_callback:
        registry.progress_callback(step, detail)

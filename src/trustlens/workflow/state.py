"""
TrustLens LangGraph State Definition.

Defines the TypedDict state that flows through the investigation workflow.
Uses TypedDict for LangGraph compatibility.
"""

from __future__ import annotations

from typing import Any, TypedDict


class InvestigationState(TypedDict, total=False):
    """State for the TrustLens investigation LangGraph workflow.

    Each field is populated by a specific node in the graph.
    Uses total=False so fields can be added incrementally.
    """

    # ── Input ───────────────────────────────────────────────────────
    original_claim: str
    claim_type: str  # ClaimType value

    # ── Claim Analysis ──────────────────────────────────────────────
    decomposition: dict  # ClaimDecomposition as dict
    atomic_claims: list[dict]

    # ── Investigation Plan ──────────────────────────────────────────
    investigation_plan: dict
    search_tasks: list[dict]

    # ── Search Results ──────────────────────────────────────────────
    raw_search_results: list[dict]
    search_calls_made: int
    engines_used: list[str]

    # ── Evidence ────────────────────────────────────────────────────
    evidence_collection: list[dict]
    claim_findings: list[dict]

    # ── Gap Detection ───────────────────────────────────────────────
    evidence_gaps: list[dict]
    needs_second_search: bool

    # ── Targeted Search ─────────────────────────────────────────────
    second_search_results: list[dict]
    second_search_evidence: list[dict]

    # ── Risk Analysis ───────────────────────────────────────────────
    risk_indicators: list[dict]
    limitations: list[str]

    # ── Report ──────────────────────────────────────────────────────
    report: dict
    methodology_note: str

    # ── Control Flow ────────────────────────────────────────────────
    current_step: str
    error: str

    # ── Injected Dependencies (prefixed with _) ─────────────────────
    _settings: Any
    _llm: Any
    _serpapi: Any

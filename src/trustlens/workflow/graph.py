"""
TrustLens LangGraph Investigation Workflow.

Orchestrates the full claim investigation pipeline:
  understand_claim → decompose → plan → search → map_evidence
  → detect_gaps → (targeted_search) → analyze_risks → generate_report

Each node is a pure function that takes state and returns state updates.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langgraph.graph import END, StateGraph

from trustlens.workflow.state import InvestigationState

from trustlens.config.settings import TrustLensSettings
from trustlens.domain.claims import AtomicClaim, ClaimDecomposition, ClaimType
from trustlens.domain.evidence import Evidence, EvidenceStance, Source, SourceType
from trustlens.domain.findings import (
    ClaimFinding,
    ClaimStatus,
    EvidenceGap,
    RiskIndicator,
)
from trustlens.domain.investigation import InvestigationPlan, SearchEngineType, SearchTask
from trustlens.domain.report import InvestigationReport
from trustlens.providers.llm import GeminiProvider
from trustlens.providers.normalization import deduplicate_results, normalize_domain
from trustlens.providers.serpapi import SerpApiProvider, SearchResult

logger = logging.getLogger(__name__)


# ── Node Functions ──────────────────────────────────────────────────


async def understand_claim(state: dict) -> dict:
    """Node 1: Parse and understand the user's claim."""
    logger.info("=== Node: understand_claim ===")
    claim = state["original_claim"]
    return {
        "current_step": "understand_claim",
        "original_claim": claim.strip(),
    }


async def decompose_claim(state: dict) -> dict:
    """Node 2: Decompose the claim into atomic sub-claims using Gemini."""
    logger.info("=== Node: decompose_claim ===")
    settings = state["_settings"]
    llm = state["_llm"]
    claim_text = state["original_claim"]

    decomposition = await llm.analyze_claim(claim_text)
    atomic_dicts = [ac.model_dump(mode="json") for ac in decomposition.atomic_claims]

    logger.info(
        f"Decomposed into {len(atomic_dicts)} atomic claims, "
        f"type={decomposition.claim_type.value}"
    )

    return {
        "current_step": "decompose_claim",
        "claim_type": decomposition.claim_type.value,
        "decomposition": decomposition.model_dump(mode="json"),
        "atomic_claims": atomic_dicts,
    }


async def plan_investigation(state: dict) -> dict:
    """Node 3: Create an investigation plan with engine-specific search tasks."""
    logger.info("=== Node: plan_investigation ===")
    llm = state["_llm"]

    # Reconstruct ClaimDecomposition from state
    decomp_data = state["decomposition"]
    decomposition = ClaimDecomposition.model_validate(decomp_data)

    plan = await llm.generate_investigation_plan(decomposition)

    # Cap search tasks to budget
    settings = state["_settings"]
    max_tasks = settings.max_search_calls
    tasks = plan.search_tasks[:max_tasks]

    engines = list(set(t.engine.value for t in tasks))
    logger.info(
        f"Investigation plan: {len(tasks)} search tasks across {len(engines)} engines"
    )

    return {
        "current_step": "plan_investigation",
        "investigation_plan": plan.model_dump(mode="json"),
        "search_tasks": [t.model_dump(mode="json") for t in tasks],
        "engines_used": engines,
    }


async def execute_searches(state: dict) -> dict:
    """Node 4: Execute all planned search tasks via SerpApi."""
    logger.info("=== Node: execute_searches ===")
    serpapi = state["_serpapi"]
    settings = state["_settings"]
    search_tasks = state["search_tasks"]

    all_results: list[dict] = []
    calls_made = 0
    engines_used = set()

    for task_dict in search_tasks:
        if calls_made >= settings.max_search_calls:
            logger.warning(f"Search budget exhausted ({calls_made} calls)")
            break

        engine = SearchEngineType(task_dict["engine"])
        query = task_dict["query"]

        try:
            results = await serpapi.search(
                engine=engine,
                query=query,
                num_results=settings.max_results_per_query,
            )
            for r in results:
                all_results.append(r.model_dump(mode="json"))
            calls_made += 1
            engines_used.add(engine.value)
            logger.info(f"  [{engine.value}] '{query}' → {len(results)} results")

        except Exception as exc:
            logger.error(f"Search failed for '{query}' on {engine.value}: {exc}")
            # Continue with remaining tasks — don't fail the whole investigation
            calls_made += 1

    # Deduplicate
    unique_results = deduplicate_results(
        [SearchResult.model_validate(r) for r in all_results]
    )
    unique_dicts = [r.model_dump(mode="json") for r in unique_results]

    logger.info(
        f"Search complete: {calls_made} calls, "
        f"{len(all_results)} raw results → {len(unique_dicts)} unique"
    )

    return {
        "current_step": "execute_searches",
        "raw_search_results": unique_dicts,
        "search_calls_made": calls_made,
        "engines_used": list(engines_used),
    }


async def map_evidence(state: dict) -> dict:
    """Node 5: Map search results to claims with stance classification."""
    logger.info("=== Node: map_evidence ===")
    llm = state["_llm"]
    atomic_claims = state["atomic_claims"]
    search_results = state["raw_search_results"]

    evidence_list: list[dict] = []
    claim_evidence_map: dict[str, dict[str, list[str]]] = {}

    # Initialize evidence map per claim
    for ac in atomic_claims:
        cid = ac["claim_id"]
        claim_evidence_map[cid] = {
            "supporting": [],
            "contradicting": [],
            "neutral": [],
        }

    # For each search result, classify against each atomic claim
    for result in search_results:
        passage = result.get("snippet", "")
        if not passage or len(passage.strip()) < 10:
            continue

        # Find the best matching claim (from the search task's claim_id if available)
        for ac in atomic_claims:
            try:
                stance, relevance, reasoning = await llm.classify_evidence_stance(
                    claim_text=ac["text"],
                    passage=passage,
                )

                if stance == EvidenceStance.IRRELEVANT and relevance < 0.3:
                    continue

                # Create source
                source = Source(
                    url=result.get("url", ""),
                    domain=normalize_domain(result.get("source", "")),
                    title=result.get("title", ""),
                    source_type=_infer_source_type(
                        SearchEngineType(result.get("engine", "GOOGLE_SEARCH"))
                    ),
                    retrieved_at=datetime.now(timezone.utc),
                    snippet=passage,
                )

                evidence = Evidence(
                    claim_id=ac["claim_id"],
                    source=source,
                    passage=passage,
                    stance=stance,
                    relevance_score=relevance,
                    search_engine=result.get("engine", ""),
                    search_query=result.get("title", ""),
                )

                ev_dict = evidence.model_dump(mode="json")
                evidence_list.append(ev_dict)

                # Map to claim
                cid = ac["claim_id"]
                if stance == EvidenceStance.SUPPORTING:
                    claim_evidence_map[cid]["supporting"].append(ev_dict["evidence_id"])
                elif stance == EvidenceStance.CONTRADICTING:
                    claim_evidence_map[cid]["contradicting"].append(ev_dict["evidence_id"])
                elif stance == EvidenceStance.NEUTRAL:
                    claim_evidence_map[cid]["neutral"].append(ev_dict["evidence_id"])

                break  # Map each result to first matching claim only

            except Exception as exc:
                logger.warning(f"Stance classification failed: {exc}")
                continue

    # Build claim findings
    claim_findings = []
    for ac in atomic_claims:
        cid = ac["claim_id"]
        ev_map = claim_evidence_map.get(cid, {"supporting": [], "contradicting": [], "neutral": []})

        status = _determine_claim_status(
            len(ev_map["supporting"]),
            len(ev_map["contradicting"]),
            len(ev_map["neutral"]),
        )

        finding = ClaimFinding(
            claim_id=cid,
            claim_text=ac["text"],
            status=status,
            supporting_evidence=ev_map["supporting"],
            contradicting_evidence=ev_map["contradicting"],
            neutral_evidence=ev_map["neutral"],
            summary=_generate_finding_summary(ac["text"], status, ev_map),
        )
        claim_findings.append(finding.model_dump(mode="json"))

    logger.info(
        f"Evidence mapping complete: {len(evidence_list)} evidence pieces "
        f"mapped to {len(claim_findings)} claims"
    )

    return {
        "current_step": "map_evidence",
        "evidence_collection": evidence_list,
        "claim_findings": claim_findings,
    }


async def detect_gaps(state: dict) -> dict:
    """Node 6: Identify claims with insufficient evidence."""
    logger.info("=== Node: detect_gaps ===")
    settings = state["_settings"]
    claim_findings = state["claim_findings"]

    gaps: list[dict] = []
    for finding in claim_findings:
        total_evidence = (
            len(finding.get("supporting_evidence", []))
            + len(finding.get("contradicting_evidence", []))
            + len(finding.get("neutral_evidence", []))
        )

        if total_evidence == 0:
            gap = EvidenceGap(
                claim_id=finding["claim_id"],
                claim_text=finding["claim_text"],
                gap_description=f"No evidence found for: {finding['claim_text']}",
                suggested_query=finding["claim_text"],
                suggested_engine=SearchEngineType.GOOGLE_SEARCH,
            )
            gaps.append(gap.model_dump(mode="json"))

    needs_second = len(gaps) > 0 and settings.enable_targeted_second_search

    logger.info(
        f"Gap detection: {len(gaps)} gaps found, "
        f"second search {'enabled' if needs_second else 'skipped'}"
    )

    return {
        "current_step": "detect_gaps",
        "evidence_gaps": gaps,
        "needs_second_search": needs_second,
    }


async def targeted_search(state: dict) -> dict:
    """Node 7: Execute targeted follow-up searches for evidence gaps."""
    logger.info("=== Node: targeted_search ===")
    serpapi = state["_serpapi"]
    llm = state["_llm"]
    settings = state["_settings"]
    gaps = state["evidence_gaps"]
    atomic_claims = state["atomic_claims"]

    second_results: list[dict] = []
    second_evidence: list[dict] = []
    calls_made = 0

    for gap in gaps:
        if calls_made >= settings.max_second_search_calls:
            break

        query = gap.get("suggested_query", gap.get("claim_text", ""))
        engine_str = gap.get("suggested_engine", "GOOGLE_SEARCH")
        engine = SearchEngineType(engine_str)

        try:
            results = await serpapi.search(engine=engine, query=query, num_results=5)
            calls_made += 1

            for r in results:
                r_dict = r.model_dump(mode="json")
                second_results.append(r_dict)

                passage = r.snippet
                if not passage or len(passage.strip()) < 10:
                    continue

                # Classify against the gap's claim
                try:
                    stance, relevance, _ = await llm.classify_evidence_stance(
                        claim_text=gap["claim_text"],
                        passage=passage,
                    )

                    if stance != EvidenceStance.IRRELEVANT:
                        source = Source(
                            url=r.url,
                            domain=normalize_domain(r.source),
                            title=r.title,
                            source_type=_infer_source_type(engine),
                            retrieved_at=datetime.now(timezone.utc),
                            snippet=passage,
                        )
                        evidence = Evidence(
                            claim_id=gap["claim_id"],
                            source=source,
                            passage=passage,
                            stance=stance,
                            relevance_score=relevance,
                            search_engine=engine.value,
                            search_query=query,
                        )
                        second_evidence.append(evidence.model_dump(mode="json"))
                except Exception:
                    continue

        except Exception as exc:
            logger.warning(f"Targeted search failed: {exc}")
            calls_made += 1

    logger.info(
        f"Targeted search: {calls_made} calls, "
        f"{len(second_evidence)} new evidence pieces"
    )

    return {
        "current_step": "targeted_search",
        "second_search_results": second_results,
        "second_search_evidence": second_evidence,
    }


async def analyze_risks(state: dict) -> dict:
    """Node 8: Identify risk indicators from all evidence."""
    logger.info("=== Node: analyze_risks ===")
    llm = state["_llm"]
    claim_findings = state["claim_findings"]
    evidence = state["evidence_collection"] + state.get("second_search_evidence", [])

    # Prepare summaries for LLM (limit size to avoid token overflow)
    findings_summary = json.dumps(
        [
            {
                "claim": f["claim_text"],
                "status": f["status"],
                "supporting_count": len(f.get("supporting_evidence", [])),
                "contradicting_count": len(f.get("contradicting_evidence", [])),
            }
            for f in claim_findings
        ],
        indent=2,
    )

    evidence_summary = json.dumps(
        [
            {
                "passage": e["passage"][:200],
                "source_url": e["source"]["url"],
                "source_domain": e["source"]["domain"],
                "stance": e["stance"],
                "engine": e["search_engine"],
            }
            for e in evidence[:30]  # Cap at 30 evidence pieces for context window
        ],
        indent=2,
    )

    try:
        result = await llm.analyze_risks(findings_summary, evidence_summary)
        risk_indicators = []
        for ri in result.get("risk_indicators", []):
            indicator = RiskIndicator(
                description=ri.get("description", ""),
                severity=ri.get("severity", "LOW"),
                explanation=ri.get("explanation", ""),
            )
            risk_indicators.append(indicator.model_dump(mode="json"))

        limitations = result.get("limitations", [
            "Investigation is based on publicly available web data only.",
            "Search results may not represent the complete picture.",
            "Evidence freshness depends on search engine indexing.",
        ])

    except Exception as exc:
        logger.error(f"Risk analysis failed: {exc}")
        risk_indicators = []
        limitations = [
            "Risk analysis could not be completed due to an error.",
            "Investigation is based on publicly available web data only.",
        ]

    logger.info(f"Risk analysis: {len(risk_indicators)} indicators found")

    return {
        "current_step": "analyze_risks",
        "risk_indicators": risk_indicators,
        "limitations": limitations,
    }


async def generate_report(state: dict) -> dict:
    """Node 9: Assemble the final investigation report."""
    logger.info("=== Node: generate_report ===")
    llm = state["_llm"]

    # Merge primary + second-round evidence
    all_evidence = state["evidence_collection"] + state.get("second_search_evidence", [])

    # Generate methodology note
    try:
        findings_text = ", ".join(
            f"{f['claim_text']}: {f['status']}"
            for f in state["claim_findings"]
        )
        methodology = await llm.generate_report_summary(
            state["original_claim"], findings_text
        )
    except Exception:
        methodology = (
            "This investigation was conducted using TrustLens, which searches "
            "multiple sources via SerpApi and presents evidence transparently. "
            "Results should be used as one input in your decision-making, not "
            "as a definitive determination."
        )

    # Build the report
    report = InvestigationReport(
        original_claim=state["original_claim"],
        claim_type=ClaimType(state["claim_type"]),
        investigated_at=datetime.now(timezone.utc),
        claim_findings=[ClaimFinding.model_validate(f) for f in state["claim_findings"]],
        evidence_collection=[Evidence.model_validate(e) for e in all_evidence],
        evidence_gaps=[EvidenceGap.model_validate(g) for g in state.get("evidence_gaps", [])],
        risk_indicators=[RiskIndicator.model_validate(r) for r in state.get("risk_indicators", [])],
        search_tasks_executed=[
            SearchTask.model_validate(t) for t in state.get("search_tasks", [])
        ],
        engines_used=[SearchEngineType(e) for e in state.get("engines_used", [])],
        total_sources_found=len(state.get("raw_search_results", [])),
        total_evidence_pieces=len(all_evidence),
        limitations=state.get("limitations", []),
        methodology_note=methodology,
    )

    logger.info("Investigation report generated successfully")

    return {
        "current_step": "complete",
        "report": report.model_dump(mode="json"),
        "methodology_note": methodology,
    }


# ── Helper Functions ────────────────────────────────────────────────


def _infer_source_type(engine: SearchEngineType) -> SourceType:
    """Infer source type from the search engine used."""
    mapping = {
        SearchEngineType.GOOGLE_SEARCH: SourceType.WEB_PAGE,
        SearchEngineType.GOOGLE_NEWS: SourceType.NEWS_ARTICLE,
        SearchEngineType.GOOGLE_JOBS: SourceType.JOB_LISTING,
        SearchEngineType.GOOGLE_MAPS: SourceType.BUSINESS_LISTING,
        SearchEngineType.GOOGLE_FORUMS: SourceType.FORUM_POST,
    }
    return mapping.get(engine, SourceType.UNKNOWN)


def _determine_claim_status(
    supporting: int, contradicting: int, neutral: int
) -> ClaimStatus:
    """Determine claim status from evidence counts."""
    total = supporting + contradicting + neutral
    if total == 0:
        return ClaimStatus.UNVERIFIED
    if contradicting > 0 and supporting > 0:
        return ClaimStatus.MIXED_EVIDENCE
    if contradicting > 0 and supporting == 0:
        return ClaimStatus.CONTRADICTED
    if supporting > 0 and contradicting == 0:
        if neutral > supporting:
            return ClaimStatus.PARTIALLY_VERIFIED
        return ClaimStatus.SUPPORTED
    return ClaimStatus.PARTIALLY_VERIFIED


def _generate_finding_summary(
    claim_text: str, status: ClaimStatus, ev_map: dict
) -> str:
    """Generate a brief summary for a claim finding."""
    s = len(ev_map.get("supporting", []))
    c = len(ev_map.get("contradicting", []))
    n = len(ev_map.get("neutral", []))

    if status == ClaimStatus.UNVERIFIED:
        return f"No evidence was found to verify or refute: '{claim_text}'"
    if status == ClaimStatus.SUPPORTED:
        return f"Found {s} supporting source(s) for this claim."
    if status == ClaimStatus.CONTRADICTED:
        return f"Found {c} source(s) contradicting this claim."
    if status == ClaimStatus.MIXED_EVIDENCE:
        return f"Mixed evidence: {s} supporting and {c} contradicting source(s)."
    return f"Partially verified: {s} supporting, {c} contradicting, {n} neutral source(s)."


# ── Graph Construction ──────────────────────────────────────────────


def should_do_targeted_search(state: dict) -> str:
    """Conditional edge: decide if targeted search is needed."""
    if state.get("needs_second_search", False):
        return "targeted_search"
    return "analyze_risks"


def build_investigation_graph() -> StateGraph:
    """Build and compile the TrustLens investigation LangGraph workflow.

    Returns a compiled StateGraph ready for invocation.

    Pipeline:
        understand_claim → decompose_claim → plan_investigation
        → execute_searches → map_evidence → detect_gaps
        → (targeted_search if gaps) → analyze_risks → generate_report
    """
    graph = StateGraph(InvestigationState)

    # Add nodes
    graph.add_node("understand_claim", understand_claim)
    graph.add_node("decompose_claim", decompose_claim)
    graph.add_node("plan_investigation", plan_investigation)
    graph.add_node("execute_searches", execute_searches)
    graph.add_node("map_evidence", map_evidence)
    graph.add_node("detect_gaps", detect_gaps)
    graph.add_node("targeted_search", targeted_search)
    graph.add_node("analyze_risks", analyze_risks)
    graph.add_node("generate_report", generate_report)

    # Linear edges
    graph.set_entry_point("understand_claim")
    graph.add_edge("understand_claim", "decompose_claim")
    graph.add_edge("decompose_claim", "plan_investigation")
    graph.add_edge("plan_investigation", "execute_searches")
    graph.add_edge("execute_searches", "map_evidence")
    graph.add_edge("map_evidence", "detect_gaps")

    # Conditional edge: gap detection → targeted search or skip
    graph.add_conditional_edges(
        "detect_gaps",
        should_do_targeted_search,
        {
            "targeted_search": "targeted_search",
            "analyze_risks": "analyze_risks",
        },
    )

    graph.add_edge("targeted_search", "analyze_risks")
    graph.add_edge("analyze_risks", "generate_report")
    graph.add_edge("generate_report", END)

    return graph


def create_investigation_workflow(
    settings: TrustLensSettings,
) -> Any:
    """Create and compile the investigation workflow with injected dependencies.

    Args:
        settings: Application settings with API keys and config.

    Returns:
        Compiled LangGraph workflow ready for invocation.
    """
    graph = build_investigation_graph()
    return graph.compile()

"""
TrustLens LangGraph Investigation Workflow.

Pipeline (9 nodes):
  understand_claim → decompose_claim → plan_investigation
  → execute_searches → map_evidence → detect_gaps
  → (targeted_search if gaps) → analyze_risks → generate_report

Providers are accessed via the module-level registry in state.py,
NOT passed through LangGraph state channels.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from trustlens.workflow.state import (
    InvestigationState,
    registry,
    _progress,
)
from trustlens.config.settings import TrustLensSettings
from trustlens.domain.claims import ClaimDecomposition, ClaimType
from trustlens.domain.evidence import Evidence, EvidenceStance, Source, SourceType
from trustlens.domain.findings import (
    ClaimFinding,
    ClaimStatus,
    EvidenceGap,
    RiskIndicator,
)
from trustlens.domain.investigation import InvestigationPlan, SearchEngineType, SearchTask
from trustlens.domain.report import InvestigationReport
from trustlens.providers.normalization import deduplicate_results, normalize_domain
from trustlens.providers.serpapi import SearchResult

logger = logging.getLogger(__name__)

# Hard cap on SerpApi requests per investigation (primary + targeted combined)
HARD_SEARCH_CAP = 5


# ── Node Functions ──────────────────────────────────────────────────


import re
import httpx
from urllib.parse import urlparse
from html.parser import HTMLParser

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.ignore = False
    def handle_starttag(self, tag, attrs):
        if tag in ["script", "style", "noscript", "nav", "footer", "head"]:
            self.ignore = True
    def handle_endtag(self, tag):
        if tag in ["script", "style", "noscript", "nav", "footer", "head"]:
            self.ignore = False
    def handle_data(self, data):
        if not self.ignore:
            t = data.strip()
            if t:
                self.text.append(t)

async def _fetch_url_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            parser = _TextExtractor()
            parser.feed(resp.text)
            return " ".join(parser.text)
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""

async def understand_claim(state: dict) -> dict:
    """Node 1: Parse and understand the user's claim."""
    logger.info("=== Node: understand_claim ===")
    _progress("understand_claim", "Parsing your claim...")
    
    claim_text = state["original_claim"].strip()
    urls = re.findall(r'(https?://[^\s]+)', claim_text)
    
    raw_results = []
    for url in urls:
        # Strip trailing punctuation
        url = url.rstrip('.,)"\'')
        _progress("understand_claim", f"Fetching provided URL: {url[:50]}...")
        text = await _fetch_url_text(url)
        if text:
            domain = urlparse(url).netloc
            raw_results.append({
                "title": f"Provided Context: {domain}",
                "url": url,
                "snippet": text[:15000],  # Take first 15k chars to capture main content
                "source": domain,
                "hostname": domain,
                "publication_date": None,
                "engagement_metadata": None,
                "engine": "GOOGLE_SEARCH",
                "position": 0,
                "raw_data": {"is_provided_url": True},
            })
            
    return {
        "current_step": "understand_claim",
        "original_claim": claim_text,
        "raw_search_results": raw_results,
    }


async def decompose_claim(state: dict) -> dict:
    """Node 2: Decompose the claim into atomic sub-claims using Gemini."""
    logger.info("=== Node: decompose_claim ===")
    _progress("decompose_claim", "Breaking claim into verifiable sub-claims...")
    llm = registry.llm

    import re
    clean_claim = re.sub(r'https?://[^\s]+', '', state["original_claim"]).strip()
    if not clean_claim:
        clean_claim = "Verify the main assertions made in the provided context."
        
    decomposition = await llm.analyze_claim(clean_claim)
    atomic_dicts = [ac.model_dump(mode="json") for ac in decomposition.atomic_claims]

    logger.info(
        f"Decomposed into {len(atomic_dicts)} atomic claims, "
        f"type={decomposition.claim_type.value}"
    )
    _progress(
        "decompose_claim",
        f"Found {len(atomic_dicts)} sub-claims (type: {decomposition.claim_type.value})",
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
    _progress("plan_investigation", "Planning which engines to search...")
    llm = registry.llm

    decomposition = ClaimDecomposition.model_validate(state["decomposition"])
    plan = await llm.generate_investigation_plan(decomposition)

    # Hard-cap search tasks
    cap = min(HARD_SEARCH_CAP, registry.settings.max_search_calls)
    tasks = plan.search_tasks[:cap]
    engines = list(set(t.engine.value for t in tasks))

    logger.info(f"Plan: {len(tasks)} tasks across {len(engines)} engines (cap={cap})")
    _progress(
        "plan_investigation",
        f"Will run {len(tasks)} searches across {len(engines)} engines: "
        + ", ".join(engines),
    )

    return {
        "current_step": "plan_investigation",
        "investigation_plan": plan.model_dump(mode="json"),
        "search_tasks": [t.model_dump(mode="json") for t in tasks],
        "engines_used": engines,
    }


async def execute_searches(state: dict) -> dict:
    """Node 4: Execute planned search tasks via SerpApi (hard-capped)."""
    logger.info("=== Node: execute_searches ===")
    serpapi = registry.serpapi
    search_tasks = state["search_tasks"]

    # Preserve provided-URL results from understand_claim (do NOT deduplicate these)
    provided_results = [
        r for r in state.get("raw_search_results", [])
        if r.get("raw_data", {}).get("is_provided_url") is True
    ]
    # Collect URLs from provided results to exclude from SerpApi dedup
    provided_urls = {r.get("url", "") for r in provided_results}

    serp_results: list[dict] = []
    calls_made = 0
    engines_used = set()

    for task_dict in search_tasks:
        if calls_made >= HARD_SEARCH_CAP:
            logger.warning(f"Hard search cap ({HARD_SEARCH_CAP}) reached")
            break

        engine = SearchEngineType(task_dict["engine"])
        query = task_dict["query"]
        _progress("execute_searches", f"[{calls_made+1}/{HARD_SEARCH_CAP}] Searching {engine.value}: {query[:60]}...")

        try:
            results = await serpapi.search(
                engine=engine,
                query=query,
                num_results=registry.settings.max_results_per_query,
            )
            for r in results:
                serp_results.append(r.model_dump(mode="json"))
            calls_made += 1
            engines_used.add(engine.value)
            logger.info(f"  [{engine.value}] '{query}' -> {len(results)} results")
        except Exception as exc:
            logger.error(f"Search failed for '{query}' on {engine.value}: {exc}")
            calls_made += 1  # Count failed calls against cap

    # Deduplicate only the SerpApi results, excluding provided URLs
    serp_for_dedup = [
        SearchResult.model_validate(r) for r in serp_results
        if r.get("url", "") not in provided_urls
    ]
    unique_serp = deduplicate_results(serp_for_dedup)
    unique_serp_dicts = [r.model_dump(mode="json") for r in unique_serp]

    # Combine: provided-URL results first (they are the primary source), then SerpApi
    combined = provided_results + unique_serp_dicts

    logger.info(f"Searches done: {calls_made} calls, {len(combined)} total results ({len(provided_results)} provided, {len(unique_serp_dicts)} from search)")
    _progress("execute_searches", f"Collected {len(combined)} results from {calls_made} searches + {len(provided_results)} provided URL(s)")

    return {
        "current_step": "execute_searches",
        "raw_search_results": combined,
        "search_calls_made": calls_made,
        "engines_used": list(engines_used),
    }


async def map_evidence(state: dict) -> dict:
    """Node 5: Map search results to claims with stance classification.

    Provided-URL results (from understand_claim) are classified against
    EVERY atomic claim because they are the primary evidence source.
    Other search results are classified against one claim each.
    """
    logger.info("=== Node: map_evidence ===")
    _progress("map_evidence", "Analyzing evidence stance for each result...")
    llm = registry.llm
    atomic_claims = state["atomic_claims"]
    search_results = state["raw_search_results"]

    evidence_list: list[dict] = []
    claim_evidence_map: dict[str, dict[str, list]] = {
        ac["claim_id"]: {"supporting": [], "contradicting": [], "neutral": []}
        for ac in atomic_claims
    }

    # Separate provided-URL results from SerpApi results
    provided_results = [
        r for r in search_results
        if r.get("raw_data", {}).get("is_provided_url") is True
        and r.get("snippet", "").strip()
        and len(r.get("snippet", "").strip()) >= 10
    ]
    serp_results = [
        r for r in search_results
        if not r.get("raw_data", {}).get("is_provided_url")
        and r.get("snippet", "").strip()
        and len(r.get("snippet", "").strip()) >= 10
    ]

    gemini_call_count = 0
    MAX_GEMINI_CALLS = 12  # budget for free-tier 15 RPM

    # Phase 1: Classify each provided-URL result against EVERY atomic claim
    for result in provided_results:
        passage = result["snippet"]
        for ac in atomic_claims:
            if gemini_call_count >= MAX_GEMINI_CALLS:
                break
            _progress("map_evidence", f"Checking provided URL against: {ac['text'][:50]}...")
            try:
                stance, relevance, reasoning, correction, excerpt = await llm.classify_evidence_stance(
                    claim_text=ac["text"],
                    passage=passage,
                )
                gemini_call_count += 1

                if stance == EvidenceStance.IRRELEVANT and relevance < 0.3:
                    continue

                source = Source(
                    url=result.get("url", ""),
                    hostname=result.get("hostname", ""),
                    title=result.get("title", ""),
                    source_type=SourceType.OFFICIAL_SITE,
                    publication_date=result.get("publication_date"),
                    engagement_metadata=result.get("engagement_metadata"),
                    retrieved_at=datetime.now(timezone.utc),
                    snippet=passage[:500],
                )

                evidence = Evidence(
                    claim_id=ac["claim_id"],
                    source=source,
                    passage=passage[:500],
                    stance=stance,
                    relevance_score=relevance,
                    search_engine="PROVIDED_URL",
                    search_query=result.get("url", ""),
                )

                ev_dict = evidence.model_dump(mode="json")
                evidence_list.append(ev_dict)

                cid = ac["claim_id"]
                if stance == EvidenceStance.SUPPORTING:
                    claim_evidence_map[cid]["supporting"].append(ev_dict["evidence_id"])
                elif stance == EvidenceStance.CONTRADICTING:
                    claim_evidence_map[cid]["contradicting"].append(ev_dict["evidence_id"])
                    claim_evidence_map[cid]["official_contradicted"] = True
                elif stance == EvidenceStance.NEUTRAL:
                    claim_evidence_map[cid]["neutral"].append(ev_dict["evidence_id"])

                if correction and "correction" not in claim_evidence_map[cid]:
                    claim_evidence_map[cid]["correction"] = str(correction)
                if excerpt and "excerpt" not in claim_evidence_map[cid]:
                    claim_evidence_map[cid]["excerpt"] = str(excerpt)
                    claim_evidence_map[cid]["source_url"] = result.get("url", "")
                    claim_evidence_map[cid]["source_title"] = result.get("title", "")

            except Exception as exc:
                logger.warning(f"Stance classification for provided URL failed: {exc}")
                gemini_call_count += 1

    # Phase 2: Classify SerpApi results (one claim each, round-robin)
    serp_to_classify = serp_results[:max(0, MAX_GEMINI_CALLS - gemini_call_count)]
    for idx, result in enumerate(serp_to_classify):
        if gemini_call_count >= MAX_GEMINI_CALLS:
            break
        passage = result["snippet"]
        ac = atomic_claims[idx % len(atomic_claims)]
        _progress("map_evidence", f"Classifying search result {idx+1}/{len(serp_to_classify)}...")

        try:
            stance, relevance, reasoning, correction, excerpt = await llm.classify_evidence_stance(
                claim_text=ac["text"],
                passage=passage,
            )
            gemini_call_count += 1

            if stance == EvidenceStance.IRRELEVANT and relevance < 0.3:
                continue

            source = Source(
                url=result.get("url", ""),
                hostname=result.get("hostname", ""),
                title=result.get("title", ""),
                source_type=_infer_source_type(
                    SearchEngineType(result.get("engine", "GOOGLE_SEARCH"))
                ),
                publication_date=result.get("publication_date"),
                engagement_metadata=result.get("engagement_metadata"),
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

            cid = ac["claim_id"]
            if stance == EvidenceStance.SUPPORTING:
                claim_evidence_map[cid]["supporting"].append(ev_dict["evidence_id"])
            elif stance == EvidenceStance.CONTRADICTING:
                claim_evidence_map[cid]["contradicting"].append(ev_dict["evidence_id"])
            elif stance == EvidenceStance.NEUTRAL:
                claim_evidence_map[cid]["neutral"].append(ev_dict["evidence_id"])

            if correction and "correction" not in claim_evidence_map[cid]:
                claim_evidence_map[cid]["correction"] = str(correction)
            if excerpt and "excerpt" not in claim_evidence_map[cid]:
                claim_evidence_map[cid]["excerpt"] = str(excerpt)
                claim_evidence_map[cid]["source_url"] = result.get("url", "")
                claim_evidence_map[cid]["source_title"] = result.get("title", "")

        except Exception as exc:
            logger.warning(f"Stance classification failed: {exc}")
            gemini_call_count += 1

    # Build claim findings
    claim_findings = []
    for ac in atomic_claims:
        cid = ac["claim_id"]
        ev_map = claim_evidence_map.get(cid, {"supporting": [], "contradicting": [], "neutral": []})
        official_contradicted = ev_map.get("official_contradicted", False)
        status = _determine_claim_status(
            len(ev_map["supporting"]), len(ev_map["contradicting"]), len(ev_map["neutral"]),
            official_contradicted=official_contradicted,
        )
        finding = ClaimFinding(
            claim_id=cid,
            claim_text=ac["text"],
            status=status,
            supporting_evidence=ev_map["supporting"],
            contradicting_evidence=ev_map["contradicting"],
            neutral_evidence=ev_map["neutral"],
            summary=_generate_finding_summary(ac["text"], status, ev_map),
            correction=ev_map.get("correction"),
            evidence_excerpt=ev_map.get("excerpt"),
            evidence_source_url=ev_map.get("source_url"),
            evidence_source_title=ev_map.get("source_title"),
        )
        claim_findings.append(finding.model_dump(mode="json"))

    logger.info(f"Evidence mapping: {len(evidence_list)} pieces mapped to {len(claim_findings)} claims")
    _progress("map_evidence", f"Mapped {len(evidence_list)} evidence pieces to {len(claim_findings)} claims")

    return {
        "current_step": "map_evidence",
        "evidence_collection": evidence_list,
        "claim_findings": claim_findings,
    }


async def detect_gaps(state: dict) -> dict:
    """Node 6: Identify claims with insufficient evidence."""
    logger.info("=== Node: detect_gaps ===")
    _progress("detect_gaps", "Checking for evidence gaps...")

    claim_findings = state["claim_findings"]
    searches_already_made = state.get("search_calls_made", 0)
    remaining_budget = HARD_SEARCH_CAP - searches_already_made

    gaps: list[dict] = []
    for finding in claim_findings:
        direct_evidence = (
            len(finding.get("supporting_evidence", []))
            + len(finding.get("contradicting_evidence", []))
        )
        if direct_evidence == 0:
            gap = EvidenceGap(
                claim_id=finding["claim_id"],
                claim_text=finding["claim_text"],
                gap_description=f"No evidence found for: {finding['claim_text']}",
                suggested_query=finding["claim_text"],
                suggested_engine=SearchEngineType.GOOGLE_SEARCH,
            )
            gaps.append(gap.model_dump(mode="json"))

    # Only do targeted search if we have budget remaining
    needs_second = len(gaps) > 0 and remaining_budget > 0 and registry.settings.enable_targeted_second_search

    logger.info(f"Gaps: {len(gaps)}, budget remaining: {remaining_budget}, second search: {needs_second}")
    _progress("detect_gaps", f"Found {len(gaps)} gaps, {remaining_budget} searches remaining")

    return {
        "current_step": "detect_gaps",
        "evidence_gaps": gaps,
        "needs_second_search": needs_second,
    }


async def targeted_search(state: dict) -> dict:
    """Node 7: Targeted follow-up searches for evidence gaps (budget-aware)."""
    logger.info("=== Node: targeted_search ===")
    _progress("targeted_search", "Running follow-up searches for gaps...")
    serpapi = registry.serpapi
    llm = registry.llm
    gaps = state["evidence_gaps"]
    searches_already_made = state.get("search_calls_made", 0)
    remaining_budget = HARD_SEARCH_CAP - searches_already_made

    second_results: list[dict] = []
    second_evidence: list[dict] = []
    calls_made = 0

    for gap in gaps:
        if calls_made >= remaining_budget:
            break

        query = gap.get("suggested_query", gap.get("claim_text", ""))
        engine = SearchEngineType(gap.get("suggested_engine", "GOOGLE_SEARCH"))

        try:
            results = await serpapi.search(engine=engine, query=query, num_results=5)
            calls_made += 1

            for r in results[:2]:
                r_dict = r.model_dump(mode="json")
                second_results.append(r_dict)

                passage = r.snippet
                if not passage or len(passage.strip()) < 10:
                    continue

                try:
                    stance, relevance, _, correction, excerpt = await llm.classify_evidence_stance(
                        claim_text=gap["claim_text"], passage=passage,
                    )
                    if stance != EvidenceStance.IRRELEVANT:
                        source = Source(
                            url=r.url,
                            hostname=r.hostname,
                            title=r.title,
                            source_type=_infer_source_type(engine),
                            publication_date=r.publication_date,
                            engagement_metadata=r.engagement_metadata,
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

    logger.info(f"Targeted search: {calls_made} calls, {len(second_evidence)} new evidence")
    _progress("targeted_search", f"Found {len(second_evidence)} new evidence from {calls_made} follow-up searches")

    # Track which engines were actually used in follow-up
    engines_used = set(state.get("engines_used", []))
    for r in second_results:
        engines_used.add(r.get("engine", "GOOGLE_SEARCH"))

    return {
        "current_step": "targeted_search",
        "second_search_results": second_results,
        "second_search_evidence": second_evidence,
        "search_calls_made": state.get("search_calls_made", 0) + calls_made,
        "engines_used": list(engines_used),
    }


async def analyze_risks(state: dict) -> dict:
    """Node 8: Identify risk indicators from all evidence."""
    logger.info("=== Node: analyze_risks ===")
    _progress("analyze_risks", "Analyzing risk patterns...")
    llm = registry.llm
    claim_findings = state["claim_findings"]
    evidence = state["evidence_collection"] + state.get("second_search_evidence", [])

    findings_summary = json.dumps(
        [{"claim": f["claim_text"], "status": f["status"],
          "supporting": len(f.get("supporting_evidence", [])),
          "contradicting": len(f.get("contradicting_evidence", []))}
         for f in claim_findings],
        indent=2,
    )

    evidence_summary = json.dumps(
        [{"passage": e["passage"][:200], "source_url": e["source"]["url"],
          "hostname": e["source"]["hostname"], "stance": e["stance"], "engine": e["search_engine"]}
         for e in evidence[:20]],
        indent=2,
    )

    try:
        result = await llm.analyze_risks(findings_summary, evidence_summary)
        risk_indicators = [
            RiskIndicator(
                description=ri.get("description", ""),
                severity=ri.get("severity", "LOW"),
                explanation=ri.get("explanation", ""),
            ).model_dump(mode="json")
            for ri in result.get("risk_indicators", [])
        ]
        limitations = result.get("limitations", [
            "Investigation based on publicly available web data only.",
            "Search results may not represent the complete picture.",
        ])
    except Exception as exc:
        logger.error(f"Risk analysis failed: {exc}")
        risk_indicators = []
        limitations = [
            "Risk analysis could not be completed.",
            "Investigation based on publicly available web data only.",
        ]

    _progress("analyze_risks", f"Found {len(risk_indicators)} risk indicators")

    return {
        "current_step": "analyze_risks",
        "risk_indicators": risk_indicators,
        "limitations": limitations,
    }


async def generate_report(state: dict) -> dict:
    """Node 9: Assemble the final investigation report."""
    logger.info("=== Node: generate_report ===")
    _progress("generate_report", "Assembling final report...")
    llm = registry.llm

    all_evidence = state["evidence_collection"] + state.get("second_search_evidence", [])

    try:
        findings_text = ", ".join(f"{f['claim_text']}: {f['status']}" for f in state["claim_findings"])
        methodology = await llm.generate_report_summary(state["original_claim"], findings_text)
    except Exception:
        methodology = (
            "This investigation was conducted using TrustLens, which searches "
            "multiple sources via SerpApi and presents evidence transparently. "
            "Results should be used as one input in your decision-making."
        )

    statuses = [f["status"] for f in state["claim_findings"]]
    if not statuses:
        overall_status = "UNKNOWN"
    elif all(s == "CORRECT" for s in statuses):
        overall_status = "CORRECT"
    elif all(s == "INCORRECT" for s in statuses):
        overall_status = "INCORRECT"
    elif all(s == "UNVERIFIED" for s in statuses):
        overall_status = "UNVERIFIED"
    else:
        overall_status = "PARTLY CORRECT"

    report = InvestigationReport(
        original_claim=state["original_claim"],
        overall_status=overall_status,
        claim_type=ClaimType(state["claim_type"]),
        investigated_at=datetime.now(timezone.utc),
        claim_findings=[ClaimFinding.model_validate(f) for f in state["claim_findings"]],
        evidence_collection=[Evidence.model_validate(e) for e in all_evidence],
        evidence_gaps=[EvidenceGap.model_validate(g) for g in state.get("evidence_gaps", [])],
        risk_indicators=[RiskIndicator.model_validate(r) for r in state.get("risk_indicators", [])],
        search_tasks_executed=[SearchTask.model_validate(t) for t in state.get("search_tasks", [])],
        engines_used=[SearchEngineType(e) for e in state.get("engines_used", [])],
        total_sources_found=len(state.get("raw_search_results", [])) + len(state.get("second_search_results", [])),
        total_evidence_pieces=len(all_evidence),
        limitations=state.get("limitations", []),
        methodology_note=methodology,
    )

    _progress("generate_report", "Report ready!")

    return {
        "current_step": "complete",
        "report": report.model_dump(mode="json"),
        "methodology_note": methodology,
    }


# ── Helpers ─────────────────────────────────────────────────────────

def _infer_source_type(engine: SearchEngineType) -> SourceType:
    return {
        SearchEngineType.GOOGLE_SEARCH: SourceType.WEB_PAGE,
        SearchEngineType.GOOGLE_NEWS: SourceType.NEWS_ARTICLE,
        SearchEngineType.GOOGLE_JOBS: SourceType.JOB_LISTING,
        SearchEngineType.GOOGLE_MAPS: SourceType.BUSINESS_LISTING,
        SearchEngineType.GOOGLE_FORUMS: SourceType.FORUM_POST,
        SearchEngineType.GOOGLE_ADS: SourceType.OFFICIAL_SITE,
    }.get(engine, SourceType.UNKNOWN)


def _determine_claim_status(
    supporting: int, contradicting: int, neutral: int,
    *, official_contradicted: bool = False,
) -> ClaimStatus:
    """Determine the factual status of a claim.
    
    If the official/provided source directly contradicts the claim,
    it overrides any supporting evidence from other (possibly outdated) sources.
    """
    if official_contradicted:
        return ClaimStatus.INCORRECT
    if supporting == 0 and contradicting == 0:
        return ClaimStatus.UNVERIFIED
    if contradicting > 0 and supporting > 0:
        return ClaimStatus.PARTLY_CORRECT
    if contradicting > 0:
        return ClaimStatus.INCORRECT
    if supporting > 0:
        return ClaimStatus.CORRECT
    return ClaimStatus.UNVERIFIED


def _generate_finding_summary(claim_text: str, status: ClaimStatus, ev_map: dict) -> str:
    s = len(ev_map.get("supporting", []))
    c = len(ev_map.get("contradicting", []))
    n = len(ev_map.get("neutral", []))
    official = ev_map.get("official_contradicted", False)
    if status == ClaimStatus.UNVERIFIED:
        if n > 0:
            return f"Found {n} related source(s), but none directly confirm or refute this claim."
        return "No evidence was found to verify or refute this claim."
    if status == ClaimStatus.CORRECT:
        return f"This claim is correct, confirmed by {s} source(s)."
    if status == ClaimStatus.INCORRECT:
        if official and s > 0:
            return f"This claim is incorrect per the official source. {s} other source(s) repeat the wrong information."
        return f"This claim is incorrect, contradicted by {c} source(s)."
    if status == ClaimStatus.PARTLY_CORRECT:
        return f"Mixed evidence: {s} source(s) confirm and {c} source(s) contradict parts of this claim."
    return f"Evidence: {s} supporting, {c} contradicting, {n} neutral source(s)."


def should_do_targeted_search(state: dict) -> str:
    return "targeted_search" if state.get("needs_second_search", False) else "analyze_risks"


# ── Graph Construction ──────────────────────────────────────────────

def build_investigation_graph() -> StateGraph:
    """Build the 9-node TrustLens investigation pipeline."""
    graph = StateGraph(InvestigationState)

    graph.add_node("understand_claim", understand_claim)
    graph.add_node("decompose_claim", decompose_claim)
    graph.add_node("plan_investigation", plan_investigation)
    graph.add_node("execute_searches", execute_searches)
    graph.add_node("map_evidence", map_evidence)
    graph.add_node("detect_gaps", detect_gaps)
    graph.add_node("targeted_search", targeted_search)
    graph.add_node("analyze_risks", analyze_risks)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("understand_claim")
    graph.add_edge("understand_claim", "decompose_claim")
    graph.add_edge("decompose_claim", "plan_investigation")
    graph.add_edge("plan_investigation", "execute_searches")
    graph.add_edge("execute_searches", "map_evidence")
    graph.add_edge("map_evidence", "detect_gaps")
    graph.add_conditional_edges(
        "detect_gaps",
        should_do_targeted_search,
        {"targeted_search": "targeted_search", "analyze_risks": "analyze_risks"},
    )
    graph.add_edge("targeted_search", "analyze_risks")
    graph.add_edge("analyze_risks", "generate_report")
    graph.add_edge("generate_report", END)

    return graph


def create_investigation_workflow(settings: TrustLensSettings) -> Any:
    """Compile the workflow. Call configure_providers() before invoking."""
    return build_investigation_graph().compile()

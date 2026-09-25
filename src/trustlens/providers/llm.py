"""
TrustLens Gemini LLM Provider.

Uses google-genai SDK for structured output via Gemini 3.8 Flash.
All LLM interactions go through this provider for easy swapping.
"""

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from trustlens.domain.claims import AtomicClaim, ClaimDecomposition, ClaimType
from trustlens.domain.evidence import EvidenceStance
from trustlens.domain.investigation import InvestigationPlan, SearchEngineType, SearchTask

logger = logging.getLogger(__name__)


# ── Lightweight response schemas for structured Gemini output ────────
# These are simpler schemas that Gemini can reliably produce as JSON.
# We parse them and then construct our full domain models.

_DECOMPOSITION_PROMPT = """You are TrustLens, an investigation assistant that helps people assess online claims.

Analyze the following claim and decompose it into atomic sub-claims that can each be independently verified.
CRITICAL: Decompose combined statements thoroughly. For events, ensure that the organizer identity and the specific event name/version are separated into distinct checkable claims.

For each atomic claim, identify:
- The text of the specific sub-claim
- The claim type (one of: JOB_OFFER, COMPANY_CLAIM, PRODUCT_CLAIM, ONLINE_OFFER, GENERAL)
- Key entities mentioned (company names, product names, people, locations, amounts, event versions)

Also classify the overall claim type.

Respond ONLY with valid JSON matching this exact structure:
{{
    "claim_type": "JOB_OFFER | COMPANY_CLAIM | PRODUCT_CLAIM | ONLINE_OFFER | GENERAL",
    "atomic_claims": [
        {{
            "text": "the specific sub-claim text",
            "claim_type": "JOB_OFFER | COMPANY_CLAIM | PRODUCT_CLAIM | ONLINE_OFFER | GENERAL",
            "entities": ["entity1", "entity2"]
        }}
    ],
    "rationale": "explanation of why the claim was decomposed this way"
}}

CLAIM TO ANALYZE:
{claim_text}
"""

_STANCE_PROMPT = """You are TrustLens, an evidence analysis assistant.

Given a claim and an evidence passage retrieved from the web, classify the relationship between them.
CRITICAL RULES:
- ONLY mark evidence as SUPPORTING or CONTRADICTING when the source passage *directly addresses* the specific claim.
- A Maps listing for an office (e.g., Microsoft) does not, by itself, prove an event is being held there.
- Always account for whether event posts or evidence refer to the *specific edition/version* of the event mentioned in the claim.

Claim: {claim_text}

Evidence passage: {passage}

Classify the stance as one of:
- SUPPORTING: The evidence directly supports the claim
- CONTRADICTING: The evidence contradicts or undermines the claim
- NEUTRAL: The evidence is related but neither supports nor contradicts directly
- IRRELEVANT: The evidence is not related to the specific claim or edition

Also provide a relevance score from 0.0 to 1.0.

Respond ONLY with valid JSON:
{{
    "stance": "SUPPORTING | CONTRADICTING | NEUTRAL | IRRELEVANT",
    "relevance_score": 0.0 to 1.0,
    "reasoning": "brief explanation"
}}
"""

_PLAN_PROMPT = """You are TrustLens, an investigation planner.

Given the decomposed claims below, create a search plan. For each atomic claim, determine:
1. What search queries would help verify or refute it
2. Which SerpApi search engines are most appropriate

Available engines:
- GOOGLE_SEARCH: General web search for facts, company info, reviews
- GOOGLE_JOBS: Verify job listings, company hiring activity
- GOOGLE_NEWS: Check recent news coverage, press releases, scam reports
- GOOGLE_MAPS: Verify business locations, check if company has physical presence
- GOOGLE_FORUMS: Find community discussions, user experiences, complaints

IMPORTANT RULES:
- Do NOT call every engine for every claim. Select only relevant ones.
- Job/internship claims → use GOOGLE_JOBS + GOOGLE_SEARCH + GOOGLE_NEWS
- Company existence claims → use GOOGLE_MAPS + GOOGLE_SEARCH
- Salary/payment claims → use GOOGLE_SEARCH + GOOGLE_FORUMS
- Product claims → use GOOGLE_SEARCH + GOOGLE_NEWS + GOOGLE_FORUMS
- Generate 2-4 search queries per atomic claim, each targeted at a specific engine
- Write queries as a real user would search (natural language)

Decomposed claims:
{decomposition_json}

Respond ONLY with valid JSON:
{{
    "search_tasks": [
        {{
            "claim_index": 0,
            "query": "search query text",
            "engine": "GOOGLE_SEARCH | GOOGLE_JOBS | GOOGLE_NEWS | GOOGLE_MAPS | GOOGLE_FORUMS",
            "rationale": "why this engine and query"
        }}
    ],
    "reasoning": "overall investigation strategy"
}}
"""

_RISK_PROMPT = """You are TrustLens, a risk analysis assistant.

Based on the evidence gathered during an investigation, identify risk indicators.
Do NOT assign a trust score or claim the result is a scam.
Instead, flag specific concerning patterns with evidence references.

Common risk patterns to look for:
- Company has no verifiable physical address or online presence
- Job offers with unrealistic salary for the role/location
- Guarantees of placement or returns (common in scams)
- No verifiable news coverage or press releases
- Negative user reports in forums
- Mismatch between claimed company size and actual online footprint
- Request for upfront payment or personal information
- Recently registered domain
- No matching job listings on established job platforms

Claim findings:
{findings_json}

Evidence collected:
{evidence_json}

Respond ONLY with valid JSON:
{{
    "risk_indicators": [
        {{
            "description": "brief description of the risk",
            "severity": "LOW | MEDIUM | HIGH",
            "explanation": "detailed explanation with evidence references",
            "evidence_indices": [0, 1]
        }}
    ],
    "limitations": [
        "limitation 1: what we could not verify and why"
    ]
}}
"""


class GeminiProvider:
    """Gemini LLM provider for TrustLens.

    Handles all LLM-based analysis: claim decomposition, evidence stance
    classification, investigation planning, and risk analysis.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-3.8-flash"):
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._model_name = model_name
        self._client = genai.Client(api_key=api_key)
        logger.info(f"GeminiProvider initialized with model: {model_name}")

    @property
    def model_name(self) -> str:
        return self._model_name

    async def analyze_claim(self, claim_text: str) -> ClaimDecomposition:
        """Decompose a user claim into atomic, independently verifiable sub-claims.

        Args:
            claim_text: The raw claim text submitted by the user.

        Returns:
            ClaimDecomposition with atomic claims, types, and entities.
        """
        logger.info(f"Analyzing claim: '{claim_text[:80]}...'")
        prompt = _DECOMPOSITION_PROMPT.format(claim_text=claim_text)
        raw = await self._generate_json(prompt)

        # Parse into domain models
        claim_type = ClaimType(raw["claim_type"])
        atomic_claims = [
            AtomicClaim(
                text=ac["text"],
                claim_type=ClaimType(ac["claim_type"]),
                entities=ac.get("entities", []),
            )
            for ac in raw["atomic_claims"]
        ]

        return ClaimDecomposition(
            original_claim=claim_text,
            claim_type=claim_type,
            atomic_claims=atomic_claims,
            rationale=raw.get("rationale", ""),
        )

    async def classify_evidence_stance(
        self, claim_text: str, passage: str
    ) -> tuple[EvidenceStance, float, str]:
        """Classify the stance of an evidence passage relative to a claim.

        Args:
            claim_text: The claim being investigated.
            passage: The evidence passage to classify.

        Returns:
            Tuple of (stance, relevance_score, reasoning).
        """
        logger.debug("Classifying evidence stance")
        prompt = _STANCE_PROMPT.format(claim_text=claim_text, passage=passage)
        raw = await self._generate_json(prompt)

        stance = EvidenceStance(raw["stance"])
        relevance = max(0.0, min(1.0, float(raw.get("relevance_score", 0.5))))
        reasoning = raw.get("reasoning", "")
        return stance, relevance, reasoning

    async def generate_investigation_plan(
        self,
        decomposition: ClaimDecomposition,
    ) -> InvestigationPlan:
        """Create a search plan with engine-specific queries for each atomic claim.

        Args:
            decomposition: The decomposed claim with atomic sub-claims.

        Returns:
            InvestigationPlan with targeted search tasks.
        """
        logger.info("Generating investigation plan")
        decomp_json = json.dumps(
            {
                "original_claim": decomposition.original_claim,
                "claim_type": decomposition.claim_type.value,
                "atomic_claims": [
                    {
                        "index": i,
                        "text": ac.text,
                        "claim_type": ac.claim_type.value,
                        "entities": ac.entities,
                    }
                    for i, ac in enumerate(decomposition.atomic_claims)
                ],
            },
            indent=2,
        )
        prompt = _PLAN_PROMPT.format(decomposition_json=decomp_json)
        raw = await self._generate_json(prompt)

        search_tasks = []
        for task in raw.get("search_tasks", []):
            claim_index = task.get("claim_index", 0)
            claim_id = (
                decomposition.atomic_claims[claim_index].claim_id
                if claim_index < len(decomposition.atomic_claims)
                else decomposition.atomic_claims[0].claim_id
            )
            search_tasks.append(
                SearchTask(
                    claim_id=claim_id,
                    query=task["query"],
                    engine=SearchEngineType(task["engine"]),
                    rationale=task.get("rationale", ""),
                )
            )

        # Count unique engines
        engines_used = set(t.engine for t in search_tasks)

        return InvestigationPlan(
            claim_decomposition_id=decomposition.decomposition_id,
            search_tasks=search_tasks,
            total_engines_selected=len(engines_used),
            reasoning=raw.get("reasoning", ""),
        )

    async def analyze_risks(
        self,
        findings_json: str,
        evidence_json: str,
    ) -> dict[str, Any]:
        """Identify risk indicators based on evidence and findings.

        Args:
            findings_json: JSON string of claim findings.
            evidence_json: JSON string of collected evidence.

        Returns:
            Dict with risk_indicators and limitations lists.
        """
        logger.info("Analyzing risks from evidence")
        prompt = _RISK_PROMPT.format(
            findings_json=findings_json,
            evidence_json=evidence_json,
        )
        return await self._generate_json(prompt)

    async def generate_report_summary(
        self, original_claim: str, findings_summary: str
    ) -> str:
        """Generate a human-readable methodology note for the report.

        Args:
            original_claim: The original claim text.
            findings_summary: Summary of all findings.

        Returns:
            Methodology note string.
        """
        prompt = (
            f"Write a brief, neutral methodology note (2-3 sentences) for an "
            f"investigation report on this claim:\n\n'{original_claim}'\n\n"
            f"Findings summary: {findings_summary}\n\n"
            f"The note should explain that TrustLens investigated this claim "
            f"using multiple search engines, collected evidence from diverse "
            f"sources, and presents findings transparently without making a "
            f"definitive scam/legitimate determination. Mention limitations."
        )
        response = await self._generate_text(prompt)
        return response

    async def _generate_json(self, prompt: str) -> dict[str, Any]:
        """Generate structured JSON output from Gemini.

        Retries up to 3 times on 503 (overload) or 429 (rate limit) errors.
        """
        return await self._call_with_retry(prompt, json_mode=True)

    async def _generate_text(self, prompt: str) -> str:
        """Generate plain text output from Gemini.

        Retries up to 3 times on 503 (overload) or 429 (rate limit) errors.
        """
        result = await self._call_with_retry(prompt, json_mode=False)
        return result if isinstance(result, str) else json.dumps(result)

    async def _call_with_retry(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        max_retries: int = 5,
        base_delay: float = 3.0,
    ) -> Any:
        """Core Gemini call with bounded exponential backoff for transient errors."""
        import asyncio

        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                config_kwargs: dict[str, Any] = {}
                if json_mode:
                    config_kwargs["response_mime_type"] = "application/json"
                    config_kwargs["temperature"] = 0.2
                else:
                    config_kwargs["temperature"] = 0.4

                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

                if not response.text:
                    raise ValueError("Empty response from Gemini")

                if json_mode:
                    return json.loads(response.text)
                return response.text

            except json.JSONDecodeError as exc:
                logger.error(f"Failed to parse Gemini JSON response: {exc}")
                raise  # Don't retry parse errors

            except Exception as exc:
                last_error = exc
                err_str = str(exc)

                # Retry on 503/429 with exponential backoff
                if ("503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str) and attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Gemini transient error (attempt {attempt}/{max_retries}), "
                        f"retrying in {delay:.1f}s: {err_str[:100]}"
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"Gemini API error (attempt {attempt}): {exc}")
                raise

        raise last_error or RuntimeError("Gemini call failed after retries")


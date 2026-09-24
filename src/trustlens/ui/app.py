"""
TrustLens — Streamlit Investigation Dashboard.

A simple UI for submitting claims and viewing investigation reports.
Run with: streamlit run src/trustlens/ui/app.py
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ── Page Config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="TrustLens — Digital Trust Investigator",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add src to path for imports
_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from trustlens.config.settings import TrustLensSettings
from trustlens.providers.llm import GeminiProvider
from trustlens.providers.serpapi import SerpApiProvider
from trustlens.workflow.graph import create_investigation_workflow

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────

def _load_settings() -> TrustLensSettings:
    """Load settings, checking for required API keys."""
    settings = TrustLensSettings()
    return settings


def _validate_keys(settings: TrustLensSettings) -> list[str]:
    """Check which API keys are missing."""
    missing = []
    if not settings.serpapi_api_key:
        missing.append("SERPAPI_API_KEY")
    if not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    return missing


async def _run_investigation(claim: str, settings: TrustLensSettings) -> dict:
    """Run the full investigation pipeline."""
    llm = GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )
    serpapi = SerpApiProvider(
        api_key=settings.serpapi_api_key,
        timeout_seconds=settings.search_timeout_seconds,
    )

    workflow = create_investigation_workflow(settings)

    # Initial state with injected dependencies
    initial_state = {
        "original_claim": claim,
        "claim_type": "",
        "decomposition": None,
        "atomic_claims": [],
        "investigation_plan": None,
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
        "report": None,
        "methodology_note": "",
        "current_step": "starting",
        "error": None,
        "messages": [],
        # Inject providers via state (accessible in nodes)
        "_settings": settings,
        "_llm": llm,
        "_serpapi": serpapi,
    }

    result = await workflow.ainvoke(initial_state)
    return result


# ── UI Components ───────────────────────────────────────────────────


def render_sidebar():
    """Render the sidebar with app info and example claims."""
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/search--v1.png", width=64)
        st.title("TrustLens")
        st.caption("Multi-Source Digital Trust Investigator")

        st.divider()

        st.markdown("### How it works")
        st.markdown(
            """
            1. 📝 **Submit** a claim to investigate
            2. 🔍 **TrustLens decomposes** it into atomic sub-claims
            3. 🗺️ **Plans** which search engines to query
            4. 🌐 **Searches** live sources via SerpApi
            5. 📊 **Maps** evidence to each claim
            6. 🔎 **Detects gaps** and does follow-up searches
            7. 📋 **Generates** a transparent investigation report
            """
        )

        st.divider()

        st.markdown("### Example Claims")
        examples = [
            "ABC Technologies is offering a remote AI internship for ₹50,000/month and guarantees placement.",
            "XYZ Corp launched a new crypto trading platform with guaranteed 30% monthly returns.",
            "GlobalTech Solutions in Bangalore is hiring 500 freshers with ₹8 LPA starting salary.",
            "MegaDeal online store offers iPhone 15 at 80% discount with free shipping across India.",
        ]
        for ex in examples:
            if st.button(ex[:60] + "...", key=ex[:30], use_container_width=True):
                st.session_state["claim_input"] = ex

        st.divider()

        st.markdown("### SerpApi Engines Used")
        st.markdown(
            """
            - 🔍 Google Search
            - 💼 Google Jobs
            - 📰 Google News
            - 📍 Google Maps
            - 💬 Google Forums
            """
        )

        st.divider()
        st.caption("Track: Knowledge & Public Interest")
        st.caption("SerpApi India Hackathon 2026")


def render_report(report: dict):
    """Render the investigation report."""
    st.markdown("---")
    st.header("🔍 Investigation Report")

    # Claim Summary
    st.subheader("📝 Claim Investigated")
    st.info(report.get("original_claim", ""))
    st.caption(f"**Claim Type:** {report.get('claim_type', 'Unknown')} | "
               f"**Investigated:** {report.get('investigated_at', '')[:19]}")

    # Evidence Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Sources Found", report.get("total_sources_found", 0))
    with col2:
        st.metric("Evidence Pieces", report.get("total_evidence_pieces", 0))
    with col3:
        st.metric("Engines Used", len(report.get("engines_used", [])))
    with col4:
        gaps = len(report.get("evidence_gaps", []))
        st.metric("Evidence Gaps", gaps)

    # Claim Findings
    st.subheader("📊 Claim-by-Claim Findings")
    for finding in report.get("claim_findings", []):
        status = finding.get("status", "UNKNOWN")
        status_emoji = {
            "SUPPORTED": "✅",
            "CONTRADICTED": "❌",
            "UNVERIFIED": "❓",
            "PARTIALLY_VERIFIED": "⚠️",
            "MIXED_EVIDENCE": "🔄",
        }.get(status, "❓")

        with st.expander(f"{status_emoji} {finding.get('claim_text', '')[:100]}", expanded=True):
            st.markdown(f"**Status:** {status_emoji} {status}")
            st.markdown(f"**Summary:** {finding.get('summary', '')}")

            s_count = len(finding.get("supporting_evidence", []))
            c_count = len(finding.get("contradicting_evidence", []))
            n_count = len(finding.get("neutral_evidence", []))

            cols = st.columns(3)
            with cols[0]:
                st.markdown(f"✅ **Supporting:** {s_count}")
            with cols[1]:
                st.markdown(f"❌ **Contradicting:** {c_count}")
            with cols[2]:
                st.markdown(f"➖ **Neutral:** {n_count}")

    # Risk Indicators
    risk_indicators = report.get("risk_indicators", [])
    if risk_indicators:
        st.subheader("⚠️ Risk Indicators")
        st.caption("These are patterns that may warrant caution — not definitive conclusions.")
        for ri in risk_indicators:
            severity = ri.get("severity", "LOW")
            sev_color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")
            with st.expander(f"{sev_color} [{severity}] {ri.get('description', '')}"):
                st.markdown(ri.get("explanation", ""))

    # Evidence Gaps
    gaps = report.get("evidence_gaps", [])
    if gaps:
        st.subheader("🔎 Evidence Gaps")
        st.caption("Claims for which no evidence could be found.")
        for gap in gaps:
            st.warning(f"**{gap.get('claim_text', '')}**\n\n{gap.get('gap_description', '')}")

    # Evidence Collection
    evidence = report.get("evidence_collection", [])
    if evidence:
        st.subheader("📚 Evidence Sources")
        st.caption(f"Showing {len(evidence)} evidence pieces from live search results.")
        for i, ev in enumerate(evidence):
            source = ev.get("source", {})
            stance = ev.get("stance", "NEUTRAL")
            stance_emoji = {
                "SUPPORTING": "✅",
                "CONTRADICTING": "❌",
                "NEUTRAL": "➖",
            }.get(stance, "❓")

            with st.expander(
                f"{stance_emoji} [{ev.get('search_engine', '')}] "
                f"{source.get('title', 'Unknown source')[:80]}",
            ):
                st.markdown(f"**URL:** [{source.get('url', '')}]({source.get('url', '')})")
                st.markdown(f"**Domain:** {source.get('domain', '')}")
                st.markdown(f"**Stance:** {stance_emoji} {stance}")
                st.markdown(f"**Relevance:** {ev.get('relevance_score', 0):.2f}")
                st.markdown(f"**Passage:** {ev.get('passage', '')}")

    # Limitations
    limitations = report.get("limitations", [])
    if limitations:
        st.subheader("📌 Limitations")
        for lim in limitations:
            st.markdown(f"- {lim}")

    # Methodology
    methodology = report.get("methodology_note", "")
    if methodology:
        st.subheader("📋 Methodology")
        st.markdown(methodology)

    # Search Tasks Executed
    tasks = report.get("search_tasks_executed", [])
    if tasks:
        with st.expander(f"🔧 Search Tasks Executed ({len(tasks)})"):
            for t in tasks:
                st.markdown(
                    f"- **[{t.get('engine', '')}]** `{t.get('query', '')}` — {t.get('rationale', '')}"
                )


# ── Main App ────────────────────────────────────────────────────────


def main():
    """Main Streamlit application."""
    render_sidebar()

    st.title("🔍 TrustLens")
    st.markdown(
        "**Investigate online claims with multi-source evidence.**  \n"
        "Submit a claim about a job offer, company, product, or online offer. "
        "TrustLens will search live sources and present transparent findings."
    )

    st.warning(
        "⚠️ TrustLens presents evidence from public sources. It does NOT make "
        "definitive scam/legitimate determinations. Use the findings as one "
        "input in your decision-making.",
        icon="⚠️",
    )

    # Load settings
    settings = _load_settings()
    missing_keys = _validate_keys(settings)

    if missing_keys:
        st.error(
            f"Missing API key(s): **{', '.join(missing_keys)}**. "
            f"Please set them in your `.env` file and restart."
        )
        with st.expander("How to set up API keys"):
            st.code(
                "# Copy .env.example to .env and fill in your keys:\n"
                "cp .env.example .env\n\n"
                "# .env contents:\n"
                "SERPAPI_API_KEY=your_key_here\n"
                "GEMINI_API_KEY=your_key_here",
                language="bash",
            )
        return

    # Claim Input
    st.markdown("### Enter a claim to investigate")
    claim = st.text_area(
        "Claim",
        value=st.session_state.get("claim_input", ""),
        height=100,
        placeholder="e.g., ABC Technologies is offering a remote AI internship for ₹50,000/month and guarantees placement.",
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        investigate = st.button(
            "🔍 Investigate",
            type="primary",
            use_container_width=True,
            disabled=not claim.strip(),
        )

    if investigate and claim.strip():
        with st.status("🔍 Investigating claim...", expanded=True) as status:
            st.write("📝 Understanding claim...")

            try:
                result = asyncio.run(_run_investigation(claim.strip(), settings))

                if result.get("report"):
                    status.update(
                        label="✅ Investigation complete!",
                        state="complete",
                    )
                    st.session_state["last_report"] = result["report"]
                else:
                    status.update(
                        label="❌ Investigation did not complete",
                        state="error",
                    )
                    st.error(f"Error: {result.get('error', 'Unknown error')}")

            except Exception as exc:
                status.update(label="❌ Investigation failed", state="error")
                st.error(f"An error occurred: {str(exc)}")
                logger.exception("Investigation failed")

    # Display report
    if "last_report" in st.session_state:
        render_report(st.session_state["last_report"])


if __name__ == "__main__":
    main()

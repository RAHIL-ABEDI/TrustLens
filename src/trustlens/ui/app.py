"""
TrustLens — Streamlit Investigation Dashboard.

Run with: streamlit run src/trustlens/ui/app.py
"""

import asyncio
import logging
import sys
from pathlib import Path

import streamlit as st

# ── Page Config (must be first Streamlit call) ──────────────────────
st.set_page_config(
    page_title="TrustLens — Digital Trust Investigator",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add project root to path
_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv()

from trustlens.config.settings import TrustLensSettings
from trustlens.workflow.state import configure_providers
from trustlens.workflow.graph import create_investigation_workflow

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")


# ── Investigation Runner ────────────────────────────────────────────

def _run_investigation_sync(claim: str, settings: TrustLensSettings, status_container) -> dict:
    """Run the investigation pipeline synchronously for Streamlit.

    Uses a fresh event loop to avoid conflicts with Streamlit's own loop.
    Shows progress updates via the status_container.
    """
    progress_steps = []

    def progress_callback(step: str, detail: str):
        progress_steps.append((step, detail))
        status_container.write(f"{'🔄' if 'search' in step.lower() else '🧠'} **{step}**: {detail}")

    # Configure providers (module-level registry)
    configure_providers(settings, progress_callback=progress_callback)

    # Create and compile workflow
    workflow = create_investigation_workflow(settings)

    # Initial state (only serializable data — no providers)
    initial_state = {
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

    # Run async workflow in a fresh loop
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(workflow.ainvoke(initial_state))
        return result
    finally:
        loop.close()


def _test_gemini_sync(settings: TrustLensSettings) -> None:
    """Make one minimal structured-JSON Gemini API request. Raises Exception on failure."""
    from trustlens.providers.llm import GeminiProvider
    
    async def do_test():
        llm = GeminiProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
        )
        prompt = 'Respond with JSON: {"status": "ok"}'
        # Using a direct call or _generate_json to test
        return await llm._generate_json(prompt)
    
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(do_test())
    finally:
        loop.close()



# ── Sidebar ─────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("🔍 TrustLens")
        st.caption("Multi-Source Digital Trust Investigator")
        st.divider()

        st.markdown("### How it works")
        st.markdown(
            "1. 📝 Submit a claim to investigate\n"
            "2. 🧠 AI decomposes it into sub-claims\n"
            "3. 🗺️ Plans which SerpApi engines to query\n"
            "4. 🌐 Searches live sources (max 5 calls)\n"
            "5. 📊 Maps evidence to each claim\n"
            "6. 🔎 Detects gaps, does follow-up searches\n"
            "7. 📋 Generates transparent report"
        )
        st.divider()

        st.markdown("### Example Claims")
        examples = [
            "ABC Technologies is offering a remote AI internship for ₹50,000/month and guarantees placement.",
            "XYZ Corp launched a new crypto trading platform with guaranteed 30% monthly returns.",
            "GlobalTech Solutions in Bangalore is hiring 500 freshers with ₹8 LPA starting salary.",
        ]
        for i, ex in enumerate(examples):
            if st.button(ex[:55] + "...", key=f"example_{i}", use_container_width=True):
                st.session_state["claim_input"] = ex

        st.divider()
        st.markdown("### SerpApi Engines")
        st.markdown(
            "- 🔍 Google Search\n"
            "- 💼 Google Jobs\n"
            "- 📰 Google News\n"
            "- 📍 Google Maps\n"
            "- 💬 Google Forums"
        )
        st.divider()
        st.caption("Track: Knowledge & Public Interest")
        st.caption("SerpApi India Hackathon 2026")


# ── Report Renderer ─────────────────────────────────────────────────

def render_report(report: dict):
    st.markdown("---")
    st.header("🔍 Investigation Report")

    # ── Claim Summary
    st.subheader("📝 Claim Investigated")
    st.info(report.get("original_claim", ""))

    claim_type = report.get("claim_type", "GENERAL")
    timestamp = str(report.get("investigated_at", ""))[:19]
    st.caption(f"**Type:** {claim_type} | **Time:** {timestamp}")

    # ── Stats
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sources Found", report.get("total_sources_found", 0))
    col2.metric("Evidence Pieces", report.get("total_evidence_pieces", 0))
    col3.metric("Engines Used", len(report.get("engines_used", [])))
    col4.metric("Evidence Gaps", len(report.get("evidence_gaps", [])))

    # ── Engines Used
    engines = report.get("engines_used", [])
    if engines:
        engine_labels = {
            "GOOGLE_SEARCH": "🔍 Google Search",
            "GOOGLE_JOBS": "💼 Google Jobs",
            "GOOGLE_NEWS": "📰 Google News",
            "GOOGLE_MAPS": "📍 Google Maps",
            "GOOGLE_FORUMS": "💬 Google Forums",
        }
        st.markdown("**SerpApi Engines Used:** " + " · ".join(
            engine_labels.get(e, e) for e in engines
        ))

    # ── Claim Findings
    st.subheader("📊 Claim-by-Claim Findings")
    status_emoji = {
        "SUPPORTED": "✅", "CONTRADICTED": "❌", "UNVERIFIED": "❓",
        "PARTIALLY_VERIFIED": "⚠️", "MIXED_EVIDENCE": "🔄",
    }
    for finding in report.get("claim_findings", []):
        status = finding.get("status", "UNKNOWN")
        emoji = status_emoji.get(status, "❓")
        with st.expander(f"{emoji} {finding.get('claim_text', '')[:100]}", expanded=True):
            st.markdown(f"**Status:** {emoji} {status}")
            st.markdown(f"**Summary:** {finding.get('summary', '')}")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"✅ Supporting: **{len(finding.get('supporting_evidence', []))}**")
            c2.markdown(f"❌ Contradicting: **{len(finding.get('contradicting_evidence', []))}**")
            c3.markdown(f"➖ Neutral: **{len(finding.get('neutral_evidence', []))}**")

    # ── Risk Indicators
    risks = report.get("risk_indicators", [])
    if risks:
        st.subheader("⚠️ Risk Indicators")
        st.caption("Patterns that may warrant caution — not definitive conclusions.")
        sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        for ri in risks:
            severity = ri.get("severity", "LOW")
            with st.expander(f"{sev_icon.get(severity, '⚪')} [{severity}] {ri.get('description', '')}"):
                st.markdown(ri.get("explanation", ""))

    # ── Evidence Gaps
    gaps = report.get("evidence_gaps", [])
    if gaps:
        st.subheader("🔎 Evidence Gaps")
        st.caption("Claims for which no evidence could be found.")
        for gap in gaps:
            st.warning(f"**{gap.get('claim_text', '')}**\n\n{gap.get('gap_description', '')}")

    # ── Evidence Sources (with clickable links)
    evidence = report.get("evidence_collection", [])
    if evidence:
        st.subheader("📚 Evidence Sources")
        st.caption(f"{len(evidence)} evidence pieces from live SerpApi search results.")
        stance_emoji = {"SUPPORTING": "✅", "CONTRADICTING": "❌", "NEUTRAL": "➖"}
        for ev in evidence:
            src = ev.get("source", {})
            stance = ev.get("stance", "NEUTRAL")
            emoji = stance_emoji.get(stance, "❓")
            engine = ev.get("search_engine", "")
            title = src.get("title", "Unknown")[:80]

            with st.expander(f"{emoji} [{engine}] {title}"):
                url = src.get("url", "")
                if url:
                    st.markdown(f"🔗 **Source:** [{url}]({url})")
                
                meta_parts = []
                hostname = src.get("hostname", "")
                if hostname:
                    meta_parts.append(f"**Host:** {hostname}")
                pub_date = src.get("publication_date")
                if pub_date:
                    meta_parts.append(f"**Date:** {pub_date}")
                engagement = src.get("engagement_metadata")
                if engagement:
                    meta_parts.append(f"**Engagement:** {engagement}")
                
                if meta_parts:
                    st.markdown(" | ".join(meta_parts))

                st.markdown(f"**Stance:** {emoji} {stance} | **Relevance:** {ev.get('relevance_score', 0):.2f}")
                st.markdown(f"**Passage:** {ev.get('passage', '')}")

    # ── Limitations
    limitations = report.get("limitations", [])
    if limitations:
        st.subheader("📌 Limitations")
        for lim in limitations:
            st.markdown(f"- {lim}")

    # ── Methodology
    methodology = report.get("methodology_note", "")
    if methodology:
        st.subheader("📋 Methodology")
        st.markdown(methodology)

    # ── Search Tasks (collapsed)
    tasks = report.get("search_tasks_executed", [])
    if tasks:
        with st.expander(f"🔧 Search Tasks Executed ({len(tasks)})"):
            for t in tasks:
                st.markdown(f"- **[{t.get('engine', '')}]** `{t.get('query', '')}` — {t.get('rationale', '')}")


# ── Main ────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    st.title("🔍 TrustLens")
    st.markdown(
        "**Investigate online claims with multi-source evidence.**  \n"
        "Submit a claim about a job offer, company, product, or online offer."
    )
    st.warning(
        "⚠️ TrustLens presents evidence from public sources. "
        "It does NOT make definitive scam/legitimate determinations.",
        icon="⚠️",
    )

    # Settings (never display keys)
    settings = TrustLensSettings()
    missing = []
    if not settings.serpapi_api_key or settings.serpapi_api_key == "your_serpapi_key_here":
        missing.append("SERPAPI_API_KEY")
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_key_here":
        missing.append("GEMINI_API_KEY")

    if missing:
        st.error(f"Missing API key(s): **{', '.join(missing)}**. Set them in `.env` and restart.")
        return

    st.success("✅ API keys configured. Ready to investigate.", icon="🔑")

    # Claim input
    st.markdown("### Enter a claim to investigate")
    claim = st.text_area(
        "Claim",
        value=st.session_state.get("claim_input", ""),
        height=100,
        placeholder="e.g., ABC Technologies is offering a remote AI internship for ₹50,000/month...",
        label_visibility="collapsed",
    )

    investigate = st.button(
        "🔍 Investigate",
        type="primary",
        disabled=not claim.strip(),
    )

    if investigate and claim.strip():
        with st.status("🔍 Investigating claim...", expanded=True) as status_widget:
            status_widget.write("📝 Checking Gemini API...")
            
            try:
                _test_gemini_sync(settings)
                status_widget.write("✅ Gemini API check passed.")
            except Exception as exc:
                status_widget.update(label="❌ Investigation failed", state="error")
                err_msg = str(exc)
                if settings.serpapi_api_key:
                    err_msg = err_msg.replace(settings.serpapi_api_key, "[REDACTED]")
                if settings.gemini_api_key:
                    err_msg = err_msg.replace(settings.gemini_api_key, "[REDACTED]")
                
                st.error(f"**Gemini API Error:** {err_msg}")
                st.info(f"**Required Next Step:** The configured model `{settings.gemini_model}` might be unavailable or rate-limited for your API key. Check your Google AI Studio quota, or change the model in your `.env` file and restart.")
                logger.exception("Gemini API check failed")
                return

            status_widget.write("📝 Starting investigation workflow...")

            try:
                result = _run_investigation_sync(claim.strip(), settings, status_widget)

                if result.get("report"):
                    status_widget.update(label="✅ Investigation complete!", state="complete")
                    st.session_state["last_report"] = result["report"]
                else:
                    status_widget.update(label="❌ Investigation incomplete", state="error")
                    st.error(f"Error: {result.get('error', 'Unknown')}")

            except Exception as exc:
                status_widget.update(label="❌ Investigation failed", state="error")
                err_msg = str(exc)
                # Never show API keys in error messages
                if settings.serpapi_api_key:
                    err_msg = err_msg.replace(settings.serpapi_api_key, "[REDACTED]")
                if settings.gemini_api_key:
                    err_msg = err_msg.replace(settings.gemini_api_key, "[REDACTED]")
                st.error(f"Error: {err_msg}")
                logger.exception("Investigation failed")

    # Display saved report
    if "last_report" in st.session_state:
        render_report(st.session_state["last_report"])


if __name__ == "__main__":
    main()

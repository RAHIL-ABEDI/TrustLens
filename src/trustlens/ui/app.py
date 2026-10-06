"""
TrustLens — Streamlit Investigation Dashboard.
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
    initial_sidebar_state="collapsed",
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


# ── CSS ────────────────────────────────────────────────────────────

def apply_custom_css():
    st.markdown("""
        <style>
        :root {
            --bg-color: #070B19;
            --surface-color: #111936;
            --primary-color: #7C5CFC;
            --teal-accent: #14D9A5;
            --warning-color: #FFB65E;
            --incorrect-color: #FF6577;
            --text-color: #F4F7FF;
            --muted-text: #AAB4D6;
        }
        
        /* Base page background */
        .stApp {
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 15% 50%, rgba(124, 92, 252, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 85% 30%, rgba(20, 217, 165, 0.05) 0%, transparent 50%);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        /* Glass panels */
        .glass-panel {
            background-color: rgba(17, 25, 54, 0.6);
            border: 1px solid rgba(170, 180, 214, 0.1);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            transition: transform 0.2s ease;
        }
        
        /* Hide default Streamlit elements that clutter */
        header { visibility: hidden; }
        
        /* Headers & Text */
        h1, h2, h3, h4, h5, h6, p, div, span {
            color: var(--text-color) !important;
        }
        
        .muted-text {
            color: var(--muted-text) !important;
            font-size: 0.9rem;
        }
        
        /* Inputs */
        div[data-baseweb="textarea"] {
            background-color: var(--surface-color) !important;
            border: 1px solid rgba(170, 180, 214, 0.2) !important;
            border-radius: 8px;
        }
        div[data-baseweb="textarea"] textarea {
            color: var(--text-color) !important;
            font-size: 1.1rem !important;
        }
        
        /* Primary Button */
        button[kind="primary"] {
            background-color: var(--primary-color) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.5rem 2rem !important;
            font-weight: 600 !important;
            transition: opacity 0.2s;
        }
        button[kind="primary"]:hover {
            opacity: 0.9;
        }
        
        /* Badges */
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 16px;
            font-weight: bold;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .status-badge.CORRECT { background-color: rgba(20, 217, 165, 0.15); color: var(--teal-accent) !important; border: 1px solid rgba(20, 217, 165, 0.3); }
        .status-badge.INCORRECT { background-color: rgba(255, 101, 119, 0.15); color: var(--incorrect-color) !important; border: 1px solid rgba(255, 101, 119, 0.3); }
        .status-badge.PARTLY_CORRECT { background-color: rgba(255, 182, 94, 0.15); color: var(--warning-color) !important; border: 1px solid rgba(255, 182, 94, 0.3); }
        .status-badge.UNVERIFIED { background-color: rgba(170, 180, 214, 0.15); color: var(--muted-text) !important; border: 1px solid rgba(170, 180, 214, 0.3); }
        
        /* Outline Buttons for examples */
        button[kind="secondary"] {
            background-color: transparent !important;
            border: 1px solid rgba(170, 180, 214, 0.3) !important;
            color: var(--muted-text) !important;
            border-radius: 8px !important;
            transition: all 0.2s;
        }
        button[kind="secondary"]:hover {
            border-color: var(--primary-color) !important;
            color: var(--text-color) !important;
        }
        
        /* Links */
        a {
            color: var(--primary-color) !important;
            text-decoration: none !important;
            transition: opacity 0.2s;
        }
        a:hover {
            opacity: 0.8;
            text-decoration: underline !important;
        }

        /* Expander */
        .streamlit-expanderHeader {
            background-color: rgba(17, 25, 54, 0.8) !important;
            color: var(--text-color) !important;
            border-radius: 8px;
        }
        
        hr {
            border-color: rgba(170, 180, 214, 0.1) !important;
        }
        </style>
    """, unsafe_allow_html=True)


# ── Investigation Runner ────────────────────────────────────────────

def _run_investigation_sync(claim: str, settings: TrustLensSettings, status_widget) -> dict:
    """Run the investigation pipeline synchronously for Streamlit."""
    progress_steps = []

    def progress_callback(step: str, detail: str):
        progress_steps.append((step, detail))
        # Map technical nodes to friendly UI stages
        stage = "🔍 Understanding the claim"
        if step in ["plan_investigation", "execute_searches"]:
            stage = "🌐 Finding relevant sources"
        elif step in ["map_evidence"]:
            stage = "⚖️ Checking evidence"
        elif step in ["detect_gaps", "targeted_search", "analyze_risks", "generate_report"]:
            stage = "📋 Preparing findings"
            
        status_widget.update(label=stage)
        st.caption(f"{detail}")

    # Configure providers (module-level registry)
    configure_providers(settings, progress_callback=progress_callback)
    workflow = create_investigation_workflow(settings)

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

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(workflow.ainvoke(initial_state))
    finally:
        loop.close()


# ── Render Logic ───────────────────────────────────────────────────

def render_report(report: dict):
    overall = report.get("overall_status", "UNKNOWN")
    claim_type = report.get("claim_type", "GENERAL")
    
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown(f"### Investigation Outcome")
    overall_ui = overall.replace("_", " ")
    st.markdown(f"<span class='status-badge {overall}'>{overall_ui}</span>", unsafe_allow_html=True)
    
    explanation_map = {
        "CORRECT": "The evidence directly confirms this claim.",
        "INCORRECT": "The evidence directly contradicts this claim.",
        "PARTLY_CORRECT": "The evidence confirms some parts but contradicts others.",
        "UNVERIFIED": "No reliable evidence was found to confirm or refute this claim."
    }
    st.markdown(f"<p class='muted-text' style='margin-top: 10px;'>{explanation_map.get(overall, '')}</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Claim Findings
    st.markdown("### 📝 Findings")
    for finding in report.get("claim_findings", []):
        status = finding.get("status", "UNKNOWN")
        st.markdown('<div class="glass-panel" style="padding: 16px;">', unsafe_allow_html=True)
        st.markdown(f"**{finding.get('claim_text', '')}**")
        status_ui = status.replace("_", " ")
        st.markdown(f"<span class='status-badge {status}'>{status_ui}</span>", unsafe_allow_html=True)
        st.markdown(f"<p class='muted-text' style='margin-top: 8px;'>{finding.get('summary', '')}</p>", unsafe_allow_html=True)
        
        if finding.get("correction"):
            st.markdown(f"<p style='color: var(--incorrect-color);'><strong>Correction:</strong> {finding.get('correction')}</p>", unsafe_allow_html=True)
        
        excerpt = finding.get("evidence_excerpt")
        src_url = finding.get("evidence_source_url")
        src_title = finding.get("evidence_source_title", "")
        
        if excerpt:
            st.markdown(f"*{excerpt}*")
            if src_url:
                st.markdown(f"**Source:** <a href='{src_url}' target='_blank'>{src_title or src_url}</a>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    
    with col1:
        gaps = report.get("evidence_gaps", [])
        if gaps:
            st.markdown("### 🔎 What we could not verify")
            for gap in gaps:
                st.markdown(f"<div class='glass-panel' style='padding: 12px; border-left: 3px solid var(--muted-text);'>"
                            f"<strong>{gap.get('claim_text', '')}</strong><br>"
                            f"<span class='muted-text'>{gap.get('gap_description', '')}</span></div>", 
                            unsafe_allow_html=True)
                            
    with col2:
        risks = report.get("risk_indicators", [])
        if risks:
            st.markdown("### ⚠️ Signals worth checking")
            for ri in risks:
                st.markdown(f"<div class='glass-panel' style='padding: 12px; border-left: 3px solid var(--warning-color);'>"
                            f"<strong>{ri.get('description', '')}</strong><br>"
                            f"<span class='muted-text'>{ri.get('explanation', '')}</span></div>", 
                            unsafe_allow_html=True)

    # ── Sources
    evidence = report.get("evidence_collection", [])
    if evidence:
        st.markdown(f"### 📚 Sources ({len(evidence)})")
        for ev in evidence:
            src = ev.get("source", {})
            engine = ev.get("search_engine", "")
            if engine == "GOOGLE_ADS":
                engine = "Google Ads Transparency Center"
            title = src.get("title", "Unknown")[:80]
            url = src.get("url", "")
            
            stance = ev.get("stance", "NEUTRAL")
            stance_emoji = {"SUPPORTING": "✅", "CONTRADICTING": "❌", "NEUTRAL": "➖"}.get(stance, "❓")
            
            with st.expander(f"{stance_emoji} [{engine}] {title}"):
                if url:
                    st.markdown(f"**URL:** [{url}]({url})")
                meta = [f"Stance: **{stance}**"]
                if src.get("source_type"): meta.append(f"Type: {src.get('source_type')}")
                if src.get("publication_date"): meta.append(f"Date: {src.get('publication_date')}")
                if meta:
                    st.caption(" | ".join(meta))
                st.markdown(f"> {ev.get('passage', '')}")

    # ── Methodology
    with st.expander("Methodology & Limitations"):
        st.markdown("**Methodology**")
        st.write(report.get("methodology_note", ""))
        limitations = report.get("limitations", [])
        if limitations:
            st.markdown("**Limitations**")
            for lim in limitations:
                st.markdown(f"- {lim}")


def set_claim(claim_text: str):
    st.session_state["claim_input"] = claim_text


# ── Main ──────────────────────────────────────────────────────────

def main():
    apply_custom_css()

    st.markdown("<h1 style='text-align: center; color: var(--primary-color) !important; font-size: 3rem;'>🔍 TrustLens</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; font-weight: 400; margin-bottom: 8px;'>Investigate digital claims with traceable evidence.</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 40px;' class='muted-text'>TrustLens checks evidence from live sources and does not issue a generic trust score.</p>", unsafe_allow_html=True)

    # Settings check
    try:
        settings = TrustLensSettings()
        missing = []
        if not settings.serpapi_api_key or settings.serpapi_api_key == "your_serpapi_key_here": missing.append("SERPAPI_API_KEY")
        if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_key_here": missing.append("GEMINI_API_KEY")
        
        if missing:
            st.error(f"Missing API keys in `.env`: **{', '.join(missing)}**")
            return
    except Exception as e:
        st.error("Could not load application settings.")
        return

    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    claim = st.text_area(
        "Enter a claim",
        value=st.session_state.get("claim_input", ""),
        height=120,
        placeholder="e.g., The SerpApi India Hackathon 2026 submission deadline is October 5, 2026...",
        label_visibility="collapsed",
    )
    
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        investigate = st.button("Investigate claim", type="primary", disabled=not claim.strip(), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("<p class='muted-text'>Try an example:</p>", unsafe_allow_html=True)
    ex1, ex2, ex3 = st.columns(3)
    with ex1:
        if st.button("Hackathon rules limit teams to 3 members.", use_container_width=True):
            set_claim("SerpApi India Hackathon 2026 limits teams to 3 members.")
    with ex2:
        if st.button("Crypto offer with guaranteed 30% monthly returns.", use_container_width=True):
            set_claim("XYZ Corp launched a new crypto trading platform with guaranteed 30% monthly returns.")
    with ex3:
        if st.button("Remote AI internship paying ₹50,000/month.", use_container_width=True):
            set_claim("ABC Technologies is offering a remote AI internship for ₹50,000/month and guarantees placement.")
            
    st.markdown("<br><p style='text-align: center;' class='muted-text'><b>How it works:</b> Break down claim &rarr; Search evidence &rarr; Show traceable findings</p>", unsafe_allow_html=True)

    if investigate and claim.strip():
        st.markdown("---")
        with st.status("Initializing investigation...", expanded=True) as status_widget:
            try:
                result = _run_investigation_sync(claim.strip(), settings, status_widget)
                if result.get("report"):
                    status_widget.update(label="Investigation complete", state="complete")
                    st.session_state["last_report"] = result["report"]
                else:
                    status_widget.update(label="Investigation incomplete", state="error")
                    st.error(f"Error: We could not complete the investigation. Please try again.")
            except Exception as exc:
                status_widget.update(label="Investigation failed", state="error")
                st.error("An error occurred during the investigation. Please check your network or API quota.")
                logger.error(f"Investigation error: {exc}")

    if "last_report" in st.session_state:
        render_report(st.session_state["last_report"])


if __name__ == "__main__":
    main()

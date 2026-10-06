"""
TrustLens — Premium Streamlit Investigation Dashboard.
"""

import asyncio
import logging
import sys
from pathlib import Path

import streamlit as st

# ── Page Config (must be first) ──────────────────────────────────────
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


# ── Premium CSS (Local Only, Animations, Flexbox) ──────────────────
def apply_custom_css():
    st.markdown("""
        <style>
        :root {
            --bg-color: #050814;
            --surface-color: #0E1529;
            --surface-hover: #151F3D;
            --primary-color: #7C5CFC;
            --primary-glow: rgba(124, 92, 252, 0.4);
            --teal-accent: #14D9A5;
            --warning-color: #FFB65E;
            --incorrect-color: #FF6577;
            --text-color: #F4F7FF;
            --muted-text: #8A97C3;
            --border-color: rgba(138, 151, 195, 0.15);
        }
        
        /* Base page background */
        .stApp {
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 15% 0%, rgba(124, 92, 252, 0.06) 0%, transparent 40%),
                radial-gradient(circle at 85% 100%, rgba(20, 217, 165, 0.04) 0%, transparent 40%);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }

        /* Animations */
        @keyframes slideUpFade {
            0% { opacity: 0; transform: translateY(15px); }
            100% { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes pulseGlow {
            0% { box-shadow: 0 0 0 0 var(--primary-glow); }
            70% { box-shadow: 0 0 0 10px rgba(124, 92, 252, 0); }
            100% { box-shadow: 0 0 0 0 rgba(124, 92, 252, 0); }
        }

        .animate-in { animation: slideUpFade 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; opacity: 0; }
        .delay-1 { animation-delay: 0.1s; }
        .delay-2 { animation-delay: 0.2s; }
        .delay-3 { animation-delay: 0.3s; }
        .delay-4 { animation-delay: 0.4s; }

        /* Typography */
        h1, h2, h3, h4, h5, h6, p, div, span { color: var(--text-color) !important; }
        
        .gradient-text {
            background: linear-gradient(135deg, #F4F7FF 0%, #AAB4D6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .brand-text {
            background: linear-gradient(135deg, #7C5CFC 0%, #14D9A5 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
        }
        
        .muted-text { color: var(--muted-text) !important; font-size: 0.95rem; line-height: 1.5; }
        .micro-header { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--muted-text); font-weight: 600; margin-bottom: 4px; display: block; }

        /* Glass panels */
        .glass-panel {
            background-color: rgba(14, 21, 41, 0.7);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            transition: all 0.3s ease;
        }
        
        .glass-panel:hover {
            border-color: rgba(124, 92, 252, 0.3);
            background-color: rgba(21, 31, 61, 0.8);
            transform: translateY(-2px);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.3), 0 0 20px rgba(124, 92, 252, 0.1);
        }
        
        /* Interactive Cards */
        .source-card {
            background-color: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            transition: all 0.2s;
            border-left: 4px solid var(--muted-text);
        }
        .source-card:hover { border-color: var(--primary-color); background-color: var(--surface-hover); }
        .source-card.SUP { border-left-color: var(--teal-accent); }
        .source-card.CON { border-left-color: var(--incorrect-color); }
        
        /* Hide default Streamlit elements that clutter */
        header { visibility: hidden; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: rgba(14,21,41,0.5); padding: 8px; border-radius: 12px; }
        .stTabs [data-baseweb="tab"] { border-radius: 8px !important; padding: 8px 16px !important; border: 1px solid transparent !important; }
        .stTabs [aria-selected="true"] { background-color: var(--primary-color) !important; color: white !important; border-color: rgba(255,255,255,0.1) !important; }
        
        /* Inputs & Buttons */
        div[data-baseweb="textarea"] {
            background-color: rgba(14, 21, 41, 0.8) !important;
            border: 2px solid var(--border-color) !important;
            border-radius: 12px;
            transition: border-color 0.2s;
        }
        div[data-baseweb="textarea"]:focus-within { border-color: var(--primary-color) !important; box-shadow: 0 0 0 1px var(--primary-color) !important; }
        div[data-baseweb="textarea"] textarea { color: var(--text-color) !important; font-size: 1.15rem !important; line-height: 1.6 !important; padding: 12px !important; }
        
        button[kind="primary"] {
            background: linear-gradient(135deg, #7C5CFC 0%, #5B3AEB 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 0.75rem 2rem !important;
            font-weight: 600 !important;
            font-size: 1.05rem !important;
            transition: all 0.3s !important;
            box-shadow: 0 4px 15px rgba(124, 92, 252, 0.3) !important;
        }
        button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(124, 92, 252, 0.5) !important; }
        
        /* Badges */
        .status-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            backdrop-filter: blur(4px);
        }
        .status-badge.CORRECT { background-color: rgba(20, 217, 165, 0.15); color: var(--teal-accent) !important; border: 1px solid rgba(20, 217, 165, 0.4); box-shadow: 0 0 10px rgba(20,217,165,0.1); }
        .status-badge.INCORRECT { background-color: rgba(255, 101, 119, 0.15); color: var(--incorrect-color) !important; border: 1px solid rgba(255, 101, 119, 0.4); box-shadow: 0 0 10px rgba(255,101,119,0.1); }
        .status-badge.PARTLY_CORRECT { background-color: rgba(255, 182, 94, 0.15); color: var(--warning-color) !important; border: 1px solid rgba(255, 182, 94, 0.4); box-shadow: 0 0 10px rgba(255,182,94,0.1); }
        .status-badge.UNVERIFIED { background-color: rgba(138, 151, 195, 0.15); color: #C2C9E0 !important; border: 1px solid rgba(138, 151, 195, 0.4); }
        
        /* Stance Distribution Bar */
        .stance-bar-container { display: flex; width: 100%; height: 8px; border-radius: 4px; overflow: hidden; margin-top: 12px; background-color: rgba(255,255,255,0.05); }
        .stance-sup { background-color: var(--teal-accent); transition: width 1s ease-in-out; }
        .stance-con { background-color: var(--incorrect-color); transition: width 1s ease-in-out; }
        .stance-neu { background-color: var(--muted-text); transition: width 1s ease-in-out; }

        /* KPI Flexbox */
        .kpi-row { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
        .kpi-card { flex: 1; min-width: 140px; background-color: rgba(14, 21, 41, 0.6); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; text-align: center; }
        .kpi-value { font-size: 2.2rem; font-weight: 800; color: var(--text-color); line-height: 1.1; margin-bottom: 4px; }
        
        a { color: var(--primary-color) !important; text-decoration: none !important; transition: opacity 0.2s; }
        a:hover { opacity: 0.8; text-decoration: underline !important; }
        hr { border-color: rgba(138, 151, 195, 0.1) !important; margin: 32px 0; }
        </style>
    """, unsafe_allow_html=True)


# ── Investigation Runner ────────────────────────────────────────────
def _run_investigation_sync(claim: str, settings: TrustLensSettings, status_widget) -> dict:
    progress_steps = []
    def progress_callback(step: str, detail: str):
        progress_steps.append((step, detail))
        stage = "🔍 Understanding the claim & extracting entities..."
        if step in ["plan_investigation", "execute_searches"]:
            stage = "🌐 Polling Search Engines & Aggregating Data..."
        elif step in ["map_evidence"]:
            stage = "⚖️ Cross-Referencing Evidence & Fact-Checking..."
        elif step in ["detect_gaps", "targeted_search", "analyze_risks", "generate_report"]:
            stage = "📋 Synthesizing Final Report..."
        status_widget.update(label=stage)
        st.caption(f"<span style='color: var(--primary-color);'>→</span> {detail}", unsafe_allow_html=True)

    configure_providers(settings, progress_callback=progress_callback)
    workflow = create_investigation_workflow(settings)
    initial_state = {
        "original_claim": claim, "claim_type": "", "decomposition": {}, "atomic_claims": [], "investigation_plan": {},
        "search_tasks": [], "raw_search_results": [], "search_calls_made": 0, "engines_used": [], "evidence_collection": [],
        "claim_findings": [], "evidence_gaps": [], "needs_second_search": False, "second_search_results": [],
        "second_search_evidence": [], "risk_indicators": [], "limitations": [], "report": {}, "methodology_note": "",
        "current_step": "starting", "error": "",
    }
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(workflow.ainvoke(initial_state))
    finally:
        loop.close()


# ── Report Rendering UI ─────────────────────────────────────────────
def render_metrics(report: dict):
    sources = report.get("total_sources_found", 0)
    engines = len(report.get("engines_used", []))
    gaps = len(report.get("evidence_gaps", []))
    risks = len(report.get("risk_indicators", []))
    
    html = f"""
    <div class="kpi-row animate-in delay-1">
        <div class="kpi-card">
            <div class="kpi-value" style="color: var(--primary-color);">{sources}</div>
            <div class="micro-header">Sources Checked</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{engines}</div>
            <div class="micro-header">Engines Used</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value" style="color: {'var(--warning-color)' if gaps > 0 else 'var(--muted-text)'};">{gaps}</div>
            <div class="micro-header">Unverified Gaps</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value" style="color: {'var(--incorrect-color)' if risks > 0 else 'var(--teal-accent)'};">{risks}</div>
            <div class="micro-header">Risk Signals</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_finding_card(finding: dict, delay_class: str):
    status = finding.get("status", "UNKNOWN")
    status_ui = status.replace("_", " ")
    
    sup = len(finding.get("supporting_evidence", []))
    con = len(finding.get("contradicting_evidence", []))
    neu = len(finding.get("neutral_evidence", []))
    total = sup + con + neu
    
    # Stance Bar percentages
    p_sup = (sup / total * 100) if total else 0
    p_con = (con / total * 100) if total else 0
    p_neu = (neu / total * 100) if total else 0

    stance_html = ""
    if total > 0:
        stance_html = f"""
        <div class="stance-bar-container">
            <div class="stance-sup" style="width: {p_sup}%;" title="{sup} Supporting"></div>
            <div class="stance-neu" style="width: {p_neu}%;" title="{neu} Neutral"></div>
            <div class="stance-con" style="width: {p_con}%;" title="{con} Contradicting"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--muted-text); margin-top: 4px;">
            <span>{sup} Supports</span> <span>{con} Contradicts</span>
        </div>
        """

    correction_html = ""
    if finding.get("correction"):
        correction_html = f"<div style='margin-top: 12px; padding: 10px; background: rgba(255,101,119,0.1); border-radius: 8px; border-left: 3px solid var(--incorrect-color); color: var(--text-color);'><span class='micro-header' style='color: var(--incorrect-color);'>Correction</span>{finding.get('correction')}</div>"

    excerpt_html = ""
    excerpt = finding.get("evidence_excerpt")
    url = finding.get("evidence_source_url")
    title = finding.get("evidence_source_title") or url
    if excerpt:
        link = f" &mdash; <a href='{url}' target='_blank'>{title}</a>" if url else ""
        excerpt_html = f"<div style='margin-top: 16px; font-style: italic; color: var(--muted-text); border-left: 2px solid rgba(138,151,195,0.3); padding-left: 12px;'>\"{excerpt}\"{link}</div>"

    html = f"""
    <div class="glass-panel animate-in {delay_class}" style="padding: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px;">
            <div style="font-size: 1.1rem; font-weight: 600; line-height: 1.4;">{finding.get('claim_text', '')}</div>
            <div class="status-badge {status}">{status_ui}</div>
        </div>
        <p class="muted-text" style="margin-bottom: 12px;">{finding.get('summary', '')}</p>
        {stance_html}
        {correction_html}
        {excerpt_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_report(report: dict):
    overall = report.get("overall_status", "UNKNOWN")
    overall_ui = overall.replace("_", " ")
    
    st.markdown(f"""
    <div class="animate-in" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);">
        <div>
            <span class="micro-header">Investigation Complete</span>
            <h2 style="margin: 0; font-size: 1.8rem;" class="gradient-text">Final Outcome</h2>
        </div>
        <div class="status-badge {overall}" style="font-size: 1.2rem; padding: 10px 24px;">{overall_ui}</div>
    </div>
    """, unsafe_allow_html=True)

    tab_summary, tab_sources, tab_risks = st.tabs(["📋 Executive Summary", "📚 Evidence Tracker", "⚙️ Risks & Methodology"])

    with tab_summary:
        render_metrics(report)
        st.markdown("<h3 class='gradient-text animate-in delay-2' style='margin-bottom: 16px;'>Claim-by-Claim Breakdown</h3>", unsafe_allow_html=True)
        findings = report.get("claim_findings", [])
        for i, finding in enumerate(findings):
            delay = f"delay-{min(i+2, 4)}"
            render_finding_card(finding, delay)

    with tab_sources:
        evidence = report.get("evidence_collection", [])
        if not evidence:
            st.info("No external sources were retrieved for this claim.")
        else:
            st.markdown(f"<p class='muted-text animate-in'>Tracking {len(evidence)} verified digital traces collected across search engines.</p>", unsafe_allow_html=True)
            for i, ev in enumerate(evidence):
                delay = f"delay-{min(i%3 + 1, 4)}"
                src = ev.get("source", {})
                stance = ev.get("stance", "NEUTRAL")
                stance_class = "SUP" if stance == "SUPPORTING" else "CON" if stance == "CONTRADICTING" else "NEU"
                stance_icon = "✅" if stance == "SUPPORTING" else "❌" if stance == "CONTRADICTING" else "➖"
                
                engine = ev.get("search_engine", "")
                if engine == "GOOGLE_ADS": engine = "Google Ads Transparency Center"
                
                url = src.get("url", "#")
                title = src.get("title", "Unknown Source")[:80]
                date_str = f" • {src.get('publication_date')}" if src.get("publication_date") else ""
                
                html = f"""
                <div class="source-card {stance_class} animate-in {delay}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="micro-header" style="margin:0;">{engine} {date_str}</span>
                        <span style="font-size: 0.8rem; font-weight: 700; color: {'var(--teal-accent)' if stance=='SUPPORTING' else 'var(--incorrect-color)' if stance=='CONTRADICTING' else 'var(--muted-text)'};">{stance_icon} {stance}</span>
                    </div>
                    <a href="{url}" target="_blank" style="font-size: 1.05rem; font-weight: 600; display: block; margin-bottom: 8px;">{title}</a>
                    <p class="muted-text" style="font-size: 0.9rem; margin: 0;">"{ev.get('passage', '')}"</p>
                </div>
                """
                st.markdown(html, unsafe_allow_html=True)

    with tab_risks:
        col_gaps, col_risks = st.columns(2)
        with col_gaps:
            gaps = report.get("evidence_gaps", [])
            st.markdown("### 🔎 Unverified Claims")
            if gaps:
                for gap in gaps:
                    st.markdown(f"<div class='glass-panel animate-in delay-1' style='padding: 16px; border-top: 3px solid var(--muted-text);'>"
                                f"<div style='font-weight: 600; margin-bottom: 8px;'>{gap.get('claim_text', '')}</div>"
                                f"<span class='muted-text'>{gap.get('gap_description', '')}</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='muted-text'>All parsed claims mapped to evidence.</p>", unsafe_allow_html=True)

        with col_risks:
            risks = report.get("risk_indicators", [])
            st.markdown("### ⚠️ Risk Signals")
            if risks:
                for ri in risks:
                    st.markdown(f"<div class='glass-panel animate-in delay-2' style='padding: 16px; border-top: 3px solid var(--warning-color);'>"
                                f"<div style='font-weight: 600; margin-bottom: 8px;'>{ri.get('description', '')}</div>"
                                f"<span class='muted-text'>{ri.get('explanation', '')}</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='muted-text'>No high-risk linguistic or verifiable patterns detected.</p>", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### ⚙️ Methodology & Limitations")
        st.write(report.get("methodology_note", ""))
        for lim in report.get("limitations", []):
            st.markdown(f"- <span class='muted-text'>{lim}</span>", unsafe_allow_html=True)


def set_claim(claim_text: str):
    st.session_state["claim_input"] = claim_text


# ── Main UI Assembly ───────────────────────────────────────────────
def main():
    apply_custom_css()

    # Brand Header
    st.markdown("""
        <div class="animate-in" style="text-align: center; margin-top: 2rem; margin-bottom: 3rem;">
            <h1 style="font-size: 3.5rem; letter-spacing: -1px; margin-bottom: 0;"><span class="brand-text">TrustLens</span></h1>
            <p style="font-size: 1.25rem; font-weight: 300; margin-top: 8px;" class="gradient-text">Investigate digital claims with traceable evidence.</p>
            <p class="muted-text" style="max-width: 600px; margin: 16px auto 0 auto;">
                TrustLens autonomously searches live web data, normalizes evidence, and provides nuanced findings. 
                It does not output a generic "trust score" — it lets the evidence speak.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # Config Check
    try:
        settings = TrustLensSettings()
        missing = [k for k, v in {"SERPAPI_API_KEY": settings.serpapi_api_key, "GEMINI_API_KEY": settings.gemini_api_key}.items() if not v or v.startswith("your_")]
        if missing:
            st.error(f"Missing API keys in `.env`: **{', '.join(missing)}**")
            return
    except Exception:
        st.error("Could not load application settings.")
        return

    # Input Section
    st.markdown('<div class="glass-panel animate-in delay-1" style="max-width: 900px; margin: 0 auto;">', unsafe_allow_html=True)
    claim = st.text_area(
        "Enter a claim",
        value=st.session_state.get("claim_input", ""),
        height=140,
        placeholder="Paste a job offer, investment claim, or company policy here...\n\ne.g., The SerpApi India Hackathon 2026 submission deadline is October 5, 2026.",
        label_visibility="collapsed",
    )
    
    col_empty, col_btn = st.columns([2, 1])
    with col_btn:
        investigate = st.button("Investigate Claim", type="primary", disabled=not claim.strip(), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Examples
    st.markdown("<div class='animate-in delay-2' style='max-width: 900px; margin: 0 auto;'><span class='micro-header' style='margin-bottom: 12px; text-align: center;'>Try an example claim</span></div>", unsafe_allow_html=True)
    ex_container = st.container()
    with ex_container:
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Hackathon rules limit teams to 3 members.", use_container_width=True): set_claim("SerpApi India Hackathon 2026 limits teams to 3 members.")
        with c2:
            if st.button("Crypto platform with guaranteed 30% returns.", use_container_width=True): set_claim("XYZ Corp launched a new crypto trading platform with guaranteed 30% monthly returns.")
        with c3:
            if st.button("Remote AI internship paying ₹150k/month.", use_container_width=True): set_claim("ABC Technologies is offering a remote AI internship for ₹150,000/month and guarantees placement.")

    # Investigation Execution
    if investigate and claim.strip():
        st.markdown("<hr>", unsafe_allow_html=True)
        with st.status("Initializing Autonomous Investigation...", expanded=True) as status_widget:
            try:
                result = _run_investigation_sync(claim.strip(), settings, status_widget)
                if result.get("report"):
                    status_widget.update(label="Investigation Complete", state="complete")
                    st.session_state["last_report"] = result["report"]
                else:
                    status_widget.update(label="Investigation Incomplete", state="error")
                    st.error(f"Error: We could not complete the investigation. Please try again.")
            except Exception as exc:
                status_widget.update(label="Investigation Failed", state="error")
                st.error("An error occurred during the investigation. Please check your network or API quota.")
                logger.error(f"Investigation error: {exc}")

    # Render Report
    if "last_report" in st.session_state:
        st.markdown("<hr>", unsafe_allow_html=True)
        render_report(st.session_state["last_report"])


if __name__ == "__main__":
    main()

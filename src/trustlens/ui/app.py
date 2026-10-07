"""
TrustLens — Streamlit Investigation Desk.
"""

import asyncio
import html
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

_STYLES_PATH = Path(__file__).with_name("styles.css")

# ── Display constants ───────────────────────────────────────────────
VERDICTS = {
    "CORRECT": ("Supported", "The evidence collected leans towards supporting this claim.", "ok"),
    "INCORRECT": ("Contradicted", "The evidence collected contradicts this claim.", "bad"),
    "PARTLY_CORRECT": ("Mixed Evidence", "The available evidence is mixed. Some parts hold up, while others are contradicted.", "mixed"),
    "UNVERIFIED": ("Insufficient Evidence", "We found relevant information, but the available evidence is not strong enough to confidently support or contradict this claim.", "unknown"),
}
UNKNOWN_VERDICT = ("Unknown", "The investigation did not produce a verdict.", "unknown")

ENGINES = ["Search", "Jobs", "News", "Maps", "Forums", "Ads Transparency"]
ENGINE_LABELS = {
    "GOOGLE_SEARCH": "Google Search",
    "GOOGLE_JOBS": "Google Jobs",
    "GOOGLE_NEWS": "Google News",
    "GOOGLE_MAPS": "Google Maps",
    "GOOGLE_FORUMS": "Google Forums",
    "GOOGLE_ADS": "Ads Transparency",
}
STANCE_LABELS = {"SUPPORTING": "Supports", "CONTRADICTING": "Contradicts", "NEUTRAL": "Neutral"}
STANCE_VERDICT_CLASS = {"SUPPORTING": "CORRECT", "CONTRADICTING": "INCORRECT", "NEUTRAL": "UNVERIFIED"}

EXAMPLES = [
    ("Policy", "Hackathon rules limit teams to 3 members",
     "SerpApi India Hackathon 2026 limits teams to 3 members."),
    ("Investment", "Crypto platform with guaranteed 30% returns",
     "XYZ Corp launched a new crypto trading platform with guaranteed 30% monthly returns."),
    ("Job offer", "Remote AI internship paying ₹150k/month",
     "ABC Technologies is offering a remote AI internship for ₹150,000/month and guarantees placement."),
]

STAGES = {
    "plan_investigation": "Planning searches across live sources",
    "execute_searches": "Querying search engines",
    "map_evidence": "Cross-referencing evidence against each claim",
    "detect_gaps": "Checking for evidence gaps",
    "targeted_search": "Running targeted follow-up searches",
    "analyze_risks": "Analysing risk signals",
    "generate_report": "Writing the report",
}


# ── Helpers ─────────────────────────────────────────────────────────
def esc(value) -> str:
    """Escape untrusted text (claims, LLM output, scraped passages) for HTML."""
    return html.escape(str(value or ""), quote=True)


def render_html(markup: str) -> None:
    """Render HTML via st.markdown.

    Lines are stripped and joined so Markdown never treats indented
    HTML as a code block (the source of the raw-HTML leak).
    """
    compact = " ".join(line.strip() for line in markup.splitlines() if line.strip())
    st.markdown(compact, unsafe_allow_html=True)


def apply_custom_css() -> None:
    st.markdown(f"<style>{_STYLES_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def verdict_meta(status: str) -> tuple[str, str, str]:
    return VERDICTS.get(status, UNKNOWN_VERDICT)


def stamp(status: str, large: bool = False) -> str:
    label, _, color_class = verdict_meta(status)
    size = " lg" if large else ""
    return f'<span class="stamp{size} v-{color_class}">{esc(label)}</span>'


def section_label(text: str) -> None:
    render_html(f'<div class="section-label"><span class="t-kicker">{esc(text)}</span></div>')


# ── Investigation Runner ────────────────────────────────────────────
def _run_investigation_sync(claim: str, settings: TrustLensSettings, status_widget) -> dict:
    def progress_callback(step: str, detail: str):
        status_widget.update(label=STAGES.get(step, "Understanding the claim"))
        st.caption(f"<span class='trace-line'><span class='arrow'>→</span>{esc(detail)}</span>",
                   unsafe_allow_html=True)

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
def render_verdict_header(report: dict, claim: str) -> None:
    status = report.get("overall_status", "UNKNOWN")
    label, description, color_class = verdict_meta(status)
    claim_html = f'<div class="verdict-claim">"{esc(claim)}"</div>' if claim else ""
    
    # Calculate evidence balance
    evidence = report.get("evidence_collection", [])
    sup = sum(1 for e in evidence if e.get("stance") == "SUPPORTING")
    con = sum(1 for e in evidence if e.get("stance") == "CONTRADICTING")
    neu = sum(1 for e in evidence if e.get("stance") == "NEUTRAL")
    total = sup + con + neu
    
    balance_html = ""
    if total > 0:
        w_sup = (sup / total) * 100
        w_con = (con / total) * 100
        w_neu = (neu / total) * 100
        balance_html = f"""
        <div class="evidence-balance-card rise" style="animation-delay: 0.1s;">
            <div class="t-kicker mb-3">Evidence Balance</div>
            <div class="balance-bars">
                <div class="balance-row"><div class="b-label t-meta">Supporting</div><div class="b-track"><div class="b-fill bg-ok" style="width: {w_sup}%"></div></div><div class="b-count">{sup}</div></div>
                <div class="balance-row"><div class="b-label t-meta">Contradicting</div><div class="b-track"><div class="b-fill bg-bad" style="width: {w_con}%"></div></div><div class="b-count">{con}</div></div>
                <div class="balance-row"><div class="b-label t-meta">Contextual</div><div class="b-track"><div class="b-fill bg-unknown" style="width: {w_neu}%"></div></div><div class="b-count">{neu}</div></div>
            </div>
        </div>
        """

    sources = report.get("total_sources_found", 0)
    
    render_html(f"""
        <div class="result-header rise">
            <span class="t-kicker">Investigation Result</span>
            {claim_html}
        </div>
        
        <div class="assessment-grid">
            <section class="assessment-card v-{color_class} rise" aria-label="Overall verdict">
                <div class="assessment-top">
                    {stamp(status, large=True)}
                    <span class="t-meta">Sources examined: {sources}</span>
                </div>
                <p class="assessment-desc">{esc(description)}</p>
            </section>
            
            {balance_html}
        </div>
    """)


def render_metrics(report: dict) -> None:
    sources = report.get("total_sources_found", 0)
    engines = len(report.get("engines_used", []))
    gaps = len(report.get("evidence_gaps", []))
    risks = len(report.get("risk_indicators", []))
    cells = [
        ("Sources checked", sources, ""),
        ("Engines used", f"{engines}<span class='t-meta'> / 6</span>", ""),
        ("Unverified gaps", gaps, "is-warn" if gaps else ""),
        ("Risk signals", risks, "is-bad" if risks else ""),
    ]
    body = "".join(
        f'<div class="ledger-cell"><span class="t-kicker">{label}</span>'
        f'<div class="ledger-value {cls}">{value}</div></div>'
        for label, value, cls in cells
    )
    render_html(f'<div class="ledger rise" role="list">{body}</div>')


def render_stance(sup: int, neu: int, con: int) -> str:
    total = sup + neu + con
    if not total:
        return ""
    widths = {k: v / total * 100 for k, v in (("sup", sup), ("neu", neu), ("con", con))}
    return f"""
        <div class="stance" aria-label="{sup} supporting, {neu} neutral, {con} contradicting sources">
            <div class="stance-bar">
                <span class="s-sup" style="width:{widths['sup']:.1f}%"></span>
                <span class="s-neu" style="width:{widths['neu']:.1f}%"></span>
                <span class="s-con" style="width:{widths['con']:.1f}%"></span>
            </div>
            <div class="stance-legend">
                <span class="t-meta" style="--dot: var(--ok)">{sup} support</span>
                <span class="t-meta" style="--dot: var(--line-strong)">{neu} neutral</span>
                <span class="t-meta" style="--dot: var(--bad)">{con} contradict</span>
            </div>
        </div>
    """


def render_finding_card(finding: dict, index: int) -> None:
    status = finding.get("status", "UNKNOWN")
    _, _, color_class = verdict_meta(status)
    
    stance_html = render_stance(
        len(finding.get("supporting_evidence", [])),
        len(finding.get("neutral_evidence", [])),
        len(finding.get("contradicting_evidence", [])),
    )

    correction_html = ""
    if finding.get("correction"):
        correction_html = (
            f'<div class="correction"><span class="t-kicker">Why this assessment?</span>'
            f'<p class="t-body">{esc(finding["correction"])}</p></div>'
        )
    elif finding.get("summary"):
        correction_html = (
            f'<div class="correction"><span class="t-kicker">Why this assessment?</span>'
            f'<p class="t-body">{esc(finding["summary"])}</p></div>'
        )

    excerpt_html = ""
    excerpt = finding.get("evidence_excerpt")
    if excerpt:
        url = finding.get("evidence_source_url")
        title = finding.get("evidence_source_title") or url
        source = (
            f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer" class="source-link">{esc(title)} ↗</a>'
            if url else "Source unavailable"
        )
        excerpt_html = (
            f'<figure class="excerpt"><q>{esc(excerpt)}</q>'
            f'<figcaption class="t-meta">— {source}</figcaption></figure>'
        )

    render_html(f"""
        <article class="finding v-{color_class}">
            <div class="finding-top">
                <div>
                    <span class="t-kicker">Sub-Claim {index:02d}</span>
                    <div class="finding-claim">{esc(finding.get('claim_text', ''))}</div>
                </div>
                {stamp(status)}
            </div>
            {correction_html}
            {excerpt_html}
            {stance_html}
        </article>
    """)


def render_evidence(evidence: list) -> None:
    if not evidence:
        render_html('<div class="empty-note"><p class="t-muted">No external sources were retrieved for this claim.</p></div>')
        return

    rows = []
    for i, ev in enumerate(evidence):
        src = ev.get("source", {}) or {}
        stance = ev.get("stance", "NEUTRAL")
        engine = ENGINE_LABELS.get(ev.get("search_engine", ""), ev.get("search_engine", "") or "Web")
        url = src.get("url") or "#"
        
        # Determine source domain
        from urllib.parse import urlparse
        domain = ""
        try:
            if url != "#":
                domain = urlparse(url).netloc.replace("www.", "")
        except:
            pass
        
        title = (src.get("title") or "Untitled source")[:110]
        date = src.get("publication_date")
        date_html = f'<span class="source-date">{esc(date)}</span>' if date else ""
        
        stance_class = STANCE_VERDICT_CLASS.get(stance, "UNVERIFIED")
        _, _, color_class = verdict_meta(stance_class)
        
        rows.append(f"""
            <div class="evidence-card v-{color_class}">
                <div class="evidence-header">
                    <div class="evidence-meta">
                        <span class="evidence-badge v-{color_class}">{esc(STANCE_LABELS.get(stance, stance))}</span>
                        <span class="evidence-domain">{esc(domain)}</span>
                        <span class="t-meta">• {esc(engine)}</span>
                        {date_html}
                    </div>
                </div>
                <a class="evidence-title" href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a>
                <p class="evidence-passage">"{esc(ev.get('passage', ''))}"</p>
                <div class="evidence-actions">
                    <a href="{esc(url)}" target="_blank" rel="noopener noreferrer" class="btn-ghost">Open source ↗</a>
                </div>
            </div>
        """)
    render_html(
        f'<div class="evidence-list-header"><span class="t-heading">Sources Examined</span><span class="t-meta">{len(evidence)} live sources</span></div>'
        + '<div class="evidence-grid">' + "".join(rows) + '</div>'
    )


def render_notes(items: list, title_key: str, body_key: str, risk: bool, empty_text: str) -> None:
    if not items:
        render_html(f'<div class="empty-note"><p class="t-muted">{esc(empty_text)}</p></div>')
        return
    cls = "note is-risk" if risk else "note"
    render_html("".join(
        f'<div class="{cls}"><div class="note-title">{esc(item.get(title_key, ""))}</div>'
        f'<p class="t-muted">{esc(item.get(body_key, ""))}</p></div>'
        for item in items
    ))


def render_report(report: dict, claim: str) -> None:
    # 1 & 2 & 3: Claim, Assessment, Balance
    render_verdict_header(report, claim)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Use a two-column layout for the rest of the report
    # Left: Details & Evidence. Right: Methodology & Meta
    col_main, col_side = st.columns([1.8, 1], gap="large")
    
    with col_main:
        render_html('<div class="section-label mt-0"><span class="t-kicker">Detailed Breakdown</span></div>')
        for i, finding in enumerate(report.get("claim_findings", []), start=1):
            render_finding_card(finding, i)
        
        if not report.get("claim_findings"):
            render_html('<div class="empty-note"><p class="t-muted">No detailed sub-claims found for this investigation.</p></div>')
            
        render_html('<div class="section-label"><span class="t-kicker">Evidence</span></div>')
        render_evidence(report.get("evidence_collection", []))

    with col_side:
        render_html('<div class="section-label mt-0"><span class="t-kicker">Investigation Metadata</span></div>')
        render_metrics(report)
        
        limits = "".join(f"<li>{esc(lim)}</li>" for lim in report.get("limitations", []))
        render_html(f"""
            <div class="methodology-card mb-4">
                <div class="t-kicker mb-3">How this was generated</div>
                <div class="method-steps">
                    <span class="t-meta">🔎 Live web search</span>
                    <span class="t-meta">🤖 AI-assisted analysis</span>
                </div>
                <p class="t-body mt-3">{esc(report.get('methodology_note', ''))}</p>
                {f'<ul class="mt-2">{limits}</ul>' if limits else ''}
                <div class="mt-4 pt-3" style="border-top: 1px dashed var(--line);">
                    <span class="t-meta" style="color: var(--accent);">Powered by SerpApi (Search, Jobs, News, Maps, Forums, Ads)</span>
                </div>
            </div>
        """)

        if report.get("evidence_gaps"):
            render_html('<div class="t-kicker mb-3">Unverified Claims</div>')
            render_notes(report.get("evidence_gaps", []), "claim_text", "gap_description", False, "")
            
        if report.get("risk_indicators"):
            render_html('<div class="t-kicker mb-3">Risk Signals</div>')
            render_notes(report.get("risk_indicators", []), "description", "explanation", True, "")


# ── Input UI ────────────────────────────────────────────────────────
def set_claim(claim_text: str) -> None:
    st.session_state["claim_input"] = claim_text


def render_masthead() -> None:
    render_html("""
        <header class="masthead rise">
            <div class="logo-container">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M11 19C15.4183 19 19 15.4183 19 11C19 6.58172 15.4183 3 11 3C6.58172 3 3 6.58172 3 11C3 15.4183 6.58172 19 11 19Z" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M21.0004 20.9999L16.6504 16.6499" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M11 8V11L13 13" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <h1 class="t-display">Trust<span class="brand-mark">Lens</span></h1>
            </div>
            <div class="masthead-deck">
                <h2 class="hero-text">Investigate the evidence.</h2>
                <p class="hero-subtext">Live web search • Evidence comparison • Traceable sources</p>
            </div>
        </header>
    """)


def render_input() -> tuple[str, bool]:
    st.session_state.setdefault("claim_input", "")
    
    # Wrap in columns to constrain width and center it
    spacer1, center_col, spacer2 = st.columns([1, 4, 1])
    
    with center_col:
        render_html('<div class="input-header text-center"><span class="t-kicker">What claim do you want to investigate?</span></div>')
        
        claim = st.text_area(
            "Claim under investigation",
            key="claim_input",
            height=130,
            placeholder="Paste a claim, headline, statement, job offer, investment claim, policy statement, or other web-verifiable claim...",
            label_visibility="collapsed",
        )

        investigate = st.button("Investigate Claim", type="primary", disabled=not claim.strip(), use_container_width=True)
        
        render_html('<div class="input-header text-center mt-5"><span class="t-kicker">Try an example</span></div>')
        
        # Tighter example cards
        ex_cols = st.columns(3)
        for i, (col, (tag, label, text)) in enumerate(zip(ex_cols, EXAMPLES)):
            with col:
                st.button(f"{tag}\n\n\"{label}\"", key=f"example_{tag}", on_click=set_claim, args=(text,), use_container_width=True)
                
        render_html(
            '<div class="features-footer t-meta mt-5">'
            'Powered by <span style="color: var(--accent); font-weight: 500;">SerpApi</span> • '
            'Searches 6 Google Engines (Search, Jobs, News, Maps, Forums, Ads)'
            '</div>'
        )
                
    return claim, investigate


# ── Main UI Assembly ───────────────────────────────────────────────
def main():
    apply_custom_css()
    render_masthead()

    try:
        settings = TrustLensSettings()
        missing = [k for k, v in {"SERPAPI_API_KEY": settings.serpapi_api_key, "GEMINI_API_KEY": settings.gemini_api_key}.items() if not v or v.startswith("your_")]
        if missing:
            st.error(f"Missing API keys in `.env`: **{', '.join(missing)}**")
            return
    except Exception:
        st.error("Could not load application settings.")
        return

    claim, investigate = render_input()

    if investigate and claim.strip():
        section_label("Investigation log")
        with st.status("Understanding the claim", expanded=True) as status_widget:
            try:
                result = _run_investigation_sync(claim.strip(), settings, status_widget)
                if result.get("report"):
                    status_widget.update(label="Investigation complete", state="complete", expanded=False)
                    st.session_state["last_report"] = result["report"]
                    st.session_state["last_claim"] = claim.strip()
                else:
                    status_widget.update(label="Investigation incomplete", state="error")
                    st.error("We could not complete the investigation. Please try again.")
            except Exception as exc:
                status_widget.update(label="Investigation failed", state="error")
                st.error("Something went wrong during the investigation. Check your network connection or API quota, then try again.")
                logger.exception("Investigation error: %s", exc)

    if "last_report" in st.session_state:
        # If there's a report, show a "New Investigation" button at the top
        if st.button("← New Investigation", key="new_investigation"):
            del st.session_state["last_report"]
            st.session_state["claim_input"] = ""
            st.rerun()
            
        render_report(st.session_state["last_report"], st.session_state.get("last_claim", ""))


if __name__ == "__main__":
    main()

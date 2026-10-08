import asyncio
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from trustlens.config.settings import TrustLensSettings
from trustlens.workflow.state import configure_providers
from trustlens.workflow.graph import build_investigation_graph

def progress(step: str, detail: str):
    print(f"[{step}] {detail}")

async def run_test(name, claim):
    print(f"\n==========================================")
    print(f"TEST: {name}")
    print(f"CLAIM: '{claim}'")
    print(f"==========================================")
    
    if not claim.strip():
        print("Empty input. UI would reject this.")
        return
        
    settings = TrustLensSettings()
    configure_providers(settings, progress_callback=progress)
    graph = build_investigation_graph().compile()
    
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

    try:
        result = await graph.ainvoke(initial_state)
        report = result.get("report", {})
        print("\n--- RESULTS ---")
        print(f"Overall Status: {report.get('overall_status', 'N/A')}")
        print(f"Engines: {report.get('engines_used', [])}")
        print("Findings:")
        for f in report.get("claim_findings", []):
            print(f"  - {f['claim_text']}: {f['status']}")
    except Exception as e:
        print(f"ERROR: {e}")

async def main():
    tests = {
        "A - True Claim": "Barack Obama was the 44th president of the United States.",
        "B - False Claim": "SerpApi India Hackathon 2026 limits teams to 3 members.",
        "C - Corrected Claim": "SerpApi India Hackathon 2026 allows teams of up to 5 people.",
        "D - Insufficient Evidence": "There is a secret pink elephant hidden under the Eiffel Tower.",
        "G - Multi-part Claim": "Company ABC was founded in 2018, has 10,000 employees, and guarantees 30% annual returns on investment.",
        "H - Opinion": "The Godfather is the best movie ever made.",
        "J - Very Short Input": "Is this true?",
        "L - Special Chars": "Is it true that ₹100 is > $1 ??? & (yes/no) 🚀 \n line 2"
    }
    
    for name, claim in tests.items():
        await run_test(name, claim)

if __name__ == "__main__":
    asyncio.run(main())

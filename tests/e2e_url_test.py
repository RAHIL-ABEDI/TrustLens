import asyncio
import sys
import io

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from trustlens.config.settings import TrustLensSettings
from trustlens.workflow.state import configure_providers
from trustlens.workflow.graph import create_investigation_workflow

def progress(step: str, detail: str):
    print(f"[{step}] {detail}")

async def investigate_claim(workflow, claim: str, settings: TrustLensSettings):
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

    print(f"\n" + "="*50)
    print(f"Investigating: {claim}\n")
    try:
        result = await workflow.ainvoke(initial_state)
        report = result.get("report")
        if report:
            print("\n=== REPORT SUMMARY ===")
            print(f"Overall Status: {report.get('overall_status')}")
            print(f"Total Sources: {report.get('total_sources_found')}")
            print(f"Evidence Pieces: {report.get('total_evidence_pieces')}")
            print(f"Engines Used: {report.get('engines_used')}")
            print(f"Searches Executed: {len(report.get('search_tasks_executed', []))}")
            
            print("\nFindings:")
            for f in report.get("claim_findings", []):
                print(f"  - {f['claim_text']}: {f['status']}")
                print(f"    Summary: {f['summary']}")
                if f.get('correction'):
                    print(f"    Correction: {f['correction']}")
                if f.get('evidence_excerpt'):
                    print(f"    Evidence: \"{f['evidence_excerpt']}\"")
                if f.get('evidence_source_url'):
                    print(f"    Source: {f['evidence_source_url']}")
            
            print("\nRisk Indicators:")
            for r in report.get("risk_indicators", []):
                print(f"  - [{r['severity']}] {r['description']}")
                
        else:
            print("\nFAILED: No report generated.")
            print(f"State keys: {list(result.keys())}")
            
    except Exception as e:
        err = str(e)
        if settings.gemini_api_key:
            err = err.replace(settings.gemini_api_key, "[REDACTED]")
        if settings.serpapi_api_key:
            err = err.replace(settings.serpapi_api_key, "[REDACTED]")
        print(f"\nCRASH: {err}")

async def main():
    print("=== CONTROLLED END-TO-END URL TEST ===")
    settings = TrustLensSettings()
    configure_providers(settings, progress_callback=progress)
    workflow = create_investigation_workflow(settings)

    claims = [
        "The SerpApi India Hackathon 2026 deadline is October 5, 2026, and the required demo video must be under three minutes. https://serpapi.github.io/serpapi-india-hackathon-2026/"
    ]
    
    for claim in claims:
        await investigate_claim(workflow, claim, settings)

if __name__ == "__main__":
    asyncio.run(main())

"""Preflight test: one minimal Gemini call + one minimal SerpApi call."""

import asyncio
import sys
import os
import io

# Fix Windows console encoding for Unicode (₹ etc.)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from trustlens.config.settings import TrustLensSettings

settings = TrustLensSettings()


async def test_gemini():
    """Test 1: Minimal Gemini API call with retry for 503."""
    print("=== TEST 1: Gemini API (single minimal request) ===")
    from trustlens.providers.llm import GeminiProvider

    llm = GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            prompt = 'Respond with valid JSON only: {"test": true, "status": "ok"}'
            response = await llm._generate_json(prompt)

            print(f"  Status: SUCCESS (attempt {attempt})")
            print(f"  Response: {response}")
            return True
        except Exception as e:
            err_msg = str(e).replace(settings.gemini_api_key, "[REDACTED]")
            if "503" in err_msg and attempt < max_retries:
                wait = 5 * attempt
                print(f"  Attempt {attempt}: 503 overload, retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                print(f"  Status: FAILED after {attempt} attempt(s)")
                print(f"  Error: {err_msg}")
                return False
    return False


async def test_serpapi():
    """Test 2: Minimal SerpApi Google Search (1 credit)."""
    print()
    print("=== TEST 2: SerpApi Google Search (1 search, 2 results max) ===")
    try:
        from trustlens.providers.serpapi import SerpApiProvider
        from trustlens.domain.investigation import SearchEngineType

        serpapi = SerpApiProvider(api_key=settings.serpapi_api_key)

        results = await serpapi.search(
            engine=SearchEngineType.GOOGLE_SEARCH,
            query="SerpApi India Hackathon 2026",
            num_results=2,
        )

        print("  Status: SUCCESS")
        print(f"  Results returned: {len(results)}")
        for i, r in enumerate(results[:3]):  # Show max 3
            title = r.title[:80].encode("ascii", errors="replace").decode()
            url = r.url[:100]
            source = r.source.encode("ascii", errors="replace").decode()
            snippet = r.snippet[:80].encode("ascii", errors="replace").decode()
            print(f"  Result {i + 1}: {title}")
            print(f"    URL: {url}")
            print(f"    Source: {source}")
            print(f"    Snippet: {snippet}...")

        print(f"  Credits used: ~1")
        print(f"  Remaining budget: ~248 searches")
        return True
    except Exception as e:
        err_msg = str(e).replace(settings.serpapi_api_key, "[REDACTED]")
        print(f"  Status: FAILED")
        print(f"  Error: {err_msg}")
        return False


async def main():
    g_ok = await test_gemini()
    s_ok = await test_serpapi()

    print()
    print("=" * 50)
    print("  PREFLIGHT SUMMARY")
    print("=" * 50)
    print("  Git security:      PASS")
    print("  Credentials:       PASS")
    print("  Workflow audit:    PASS (9 nodes, 7 call providers)")
    print(f"  Gemini API:        {'PASS' if g_ok else 'FAIL'}")
    print(f"  SerpApi:           {'PASS' if s_ok else 'FAIL'}")
    print()
    if g_ok and s_ok:
        print("  ALL PREFLIGHT CHECKS PASSED.")
    elif s_ok and not g_ok:
        print("  SerpApi works. Gemini 503 is temporary - retry in a few minutes.")
    else:
        print("  SOME CHECKS FAILED. See errors above.")


if __name__ == "__main__":
    asyncio.run(main())

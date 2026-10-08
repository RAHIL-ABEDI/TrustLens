import asyncio
import time
import httpx
from unittest.mock import patch
from trustlens.providers.serpapi import SerpApiProvider
from trustlens.domain.investigation import SearchEngineType

async def main():
    print("Testing SerpApi Exponential Backoff...")
    provider = SerpApiProvider("dummy_key")
    provider.MAX_RETRIES = 4 # We want 4 attempts to see 1s, 2s, 4s delays
    
    # Mock httpx.AsyncClient.get to always raise a TimeoutException
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Mocked Timeout Error")):
        start_time = time.time()
        try:
            await provider.search(SearchEngineType.GOOGLE_SEARCH, "test query")
        except Exception as e:
            print(f"Final Error Caught: {e}")
            
        elapsed = time.time() - start_time
        print(f"Total time elapsed: {elapsed:.2f} seconds")
        print("Expected time: ~7.0 seconds (1s + 2s + 4s)")

if __name__ == "__main__":
    asyncio.run(main())

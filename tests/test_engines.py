import asyncio
from trustlens.providers.serpapi import SerpApiProvider
from trustlens.domain.investigation import SearchEngineType
from trustlens.config.settings import TrustLensSettings

async def main():
    settings = TrustLensSettings()
    provider = SerpApiProvider(settings.serpapi_api_key)
    
    # 1. Test parameter mapping (mocked)
    print("Testing Parameter Mapping...")
    p1 = provider._build_params(SearchEngineType.GOOGLE_SEARCH, "test query")
    assert p1["engine"] == "google" and p1["q"] == "test query"
    
    p2 = provider._build_params(SearchEngineType.GOOGLE_FORUMS, "test query")
    assert p2["engine"] == "google" and p2["q"] == "test query" and p2["udm"] == "18"
    
    p3 = provider._build_params(SearchEngineType.GOOGLE_ADS, "test query")
    assert p3["engine"] == "google_ads_transparency_center" and p3.get("q") is None and p3["text"] == "test query"
    
    p4 = provider._build_params(SearchEngineType.GOOGLE_ADS, "AR1234567")
    assert p4["engine"] == "google_ads_transparency_center" and p4.get("q") is None and p4["advertiser_id"] == "AR1234567"
    
    print("Parameter mappings OK.")
    
    # 2. Test Normalization (mocked)
    print("Testing Normalization...")
    mock_ads_data = {
        "advertisers": [{"name": "TestCorp", "advertiser_id": "AR999", "location": "US", "link": "http://x"}],
        "ads": [{"advertiser": {"name": "TestCorp"}, "text": "Buy now!", "ad_url": "http://y"}]
    }
    ads_results = provider._normalize_ads(mock_ads_data)
    assert len(ads_results) == 2
    assert ads_results[0].title == "Advertiser: TestCorp"
    assert ads_results[0].engine == SearchEngineType.GOOGLE_ADS
    # 2.5 Test Context Extraction Limit
    print("Testing Context Extraction...")
    from trustlens.workflow.graph import _TextExtractor, understand_claim
    # Just verify the hardcoded limit is 15000 in the code by parsing the file
    with open("src/trustlens/workflow/graph.py", "r", encoding="utf-8") as f:
        graph_code = f.read()
    assert "text[:15000]" in graph_code, "Context limit not increased to 15,000"
    print("Context extraction limit is correctly 15000.")
    
    # 3. Live tests (1 query per engine)
    print("\nExecuting live tests (1 per engine)...")
    engines = [
        (SearchEngineType.GOOGLE_SEARCH, "trustlens"),
        (SearchEngineType.GOOGLE_NEWS, "technology"),
        (SearchEngineType.GOOGLE_JOBS, "software engineer"),
        (SearchEngineType.GOOGLE_MAPS, "coffee shop"),
        (SearchEngineType.GOOGLE_FORUMS, "reddit python"),
        (SearchEngineType.GOOGLE_ADS, "Google"), # text search
    ]
    
    for engine, query in engines:
        try:
            results = await provider.search(engine, query, num_results=1)
            print(f"PASS: {engine.name} returned {len(results)} results.")
        except Exception as e:
            print(f"FAIL: {engine.name} - {str(e)}")
            
if __name__ == "__main__":
    asyncio.run(main())

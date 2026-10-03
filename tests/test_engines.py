import pytest
import asyncio
from unittest.mock import patch, MagicMock

from trustlens.domain.investigation import SearchEngineType
from trustlens.providers.serpapi import SerpApiProvider, SearchResult, SerpApiError

@pytest.fixture
def provider():
    # Use a dummy key for offline tests
    return SerpApiProvider("dummy_key")

def test_parameter_mapping(provider):
    """Test that each engine maps to the correct parameters."""
    # GOOGLE_SEARCH
    p1 = provider._build_params(SearchEngineType.GOOGLE_SEARCH, "test query")
    assert p1["engine"] == "google"
    assert p1["q"] == "test query"
    
    # GOOGLE_FORUMS
    p2 = provider._build_params(SearchEngineType.GOOGLE_FORUMS, "test query")
    assert p2["engine"] == "google_forums"
    assert p2["q"] == "test query"
    
    # GOOGLE_ADS text search
    p3 = provider._build_params(SearchEngineType.GOOGLE_ADS, "test company")
    assert p3["engine"] == "google_ads_transparency_center"
    assert "q" not in p3
    assert p3["text"] == "test company"
    
    # GOOGLE_ADS advertiser ID (matches AR format)
    p4 = provider._build_params(SearchEngineType.GOOGLE_ADS, "AR123456789012")
    assert p4["engine"] == "google_ads_transparency_center"
    assert "q" not in p4
    assert p4["advertiser_id"] == "AR123456789012"
    assert "text" not in p4
    
    # GOOGLE_ADS false advertiser ID (e.g. starts with AR but isn't digits)
    p5 = provider._build_params(SearchEngineType.GOOGLE_ADS, "ART COMPANY")
    assert p5["engine"] == "google_ads_transparency_center"
    assert "q" not in p5
    assert p5["text"] == "ART COMPANY"
    assert "advertiser_id" not in p5

def test_normalization_ads(provider):
    """Test parsing the documented Google Ads Transparency Center response."""
    mock_ads_data = {
        "advertiser": {
            "name": "Mock Advertiser",
            "advertiser_id": "AR123",
            "location": "US"
        },
        "ad_creatives": [
            {
                "text": "Buy now!",
                "ad_url": "http://x"
            },
            {
                "images": [{"url": "http://img"}],
                "ad_url": "http://y"
            }
        ]
    }
    ads_results = provider._normalize_ads(mock_ads_data)
    # The normalization should handle the exact fields.
    assert len(ads_results) == 3
    
    # Result 1: Advertiser details
    assert ads_results[0].title == "Advertiser: Mock Advertiser"
    assert "AR123" in ads_results[0].snippet
    
    # Result 2: Ad creative 1
    assert "Buy now" in ads_results[1].snippet
    assert ads_results[1].title == "Ad from Mock Advertiser"
    
    # Result 3: Ad creative 2
    assert "[Image Ad]" in ads_results[2].snippet
    assert ads_results[2].url == "http://y"
    
def test_normalization_empty(provider):
    """Test normalization handles empty results without errors."""
    assert provider._normalize_ads({}) == []
    assert provider._normalize_organic(SearchEngineType.GOOGLE_SEARCH, {}) == []

@pytest.mark.asyncio
async def test_search_error_handling(provider):
    """Test HTTP error handling."""
    from unittest.mock import AsyncMock
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        # AsyncClient context manager setup
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        
        with patch("httpx.AsyncClient.__aenter__", return_value=mock_client):
            with pytest.raises(SerpApiError, match="authentication failed"):
                await provider.search(SearchEngineType.GOOGLE_SEARCH, "test")

def test_context_extraction_limit():
    """Verify that graph.py bounds webpage extraction to 15000 characters."""
    import os
    graph_path = os.path.join(os.path.dirname(__file__), "..", "src", "trustlens", "workflow", "graph.py")
    with open(graph_path, "r", encoding="utf-8") as f:
        graph_code = f.read()
    
    # The limit logic is applied on understand_claim via text[:15000]
    assert "text[:15000]" in graph_code, "Expected single-page limit of 15000 not found."
    # The aggregate bounds are also set to 40000
    assert "MAX_AGGREGATE_CHARS = 40000" in graph_code, "Expected aggregate bound not found."

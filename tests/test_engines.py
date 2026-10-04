"""
Offline tests for TrustLens SerpApi provider and source-type mapping.

All HTTP calls are mocked – no live SerpApi requests are made.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from trustlens.domain.investigation import SearchEngineType
from trustlens.domain.evidence import SourceType
from trustlens.providers.serpapi import SerpApiProvider, SearchResult, SerpApiError
from trustlens.workflow.graph import _infer_source_type


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def provider():
    """Offline SerpApiProvider with a dummy key."""
    return SerpApiProvider("dummy_key")


# ── Parameter-mapping tests (all six engines) ─────────────────────────────────

class TestParameterMapping:
    """Assert that _build_params produces the correct engine and query fields."""

    def test_google_search(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_SEARCH, "test query")
        assert p["engine"] == "google"
        assert p["q"] == "test query"
        assert "num" in p

    def test_google_jobs(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_JOBS, "software engineer")
        assert p["engine"] == "google_jobs"
        assert p["q"] == "software engineer"

    def test_google_news(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_NEWS, "latest news")
        assert p["engine"] == "google_news"
        assert p["q"] == "latest news"
        assert "hl" in p
        assert "gl" in p

    def test_google_maps(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_MAPS, "coffee shop")
        assert p["engine"] == "google_maps"
        assert p["q"] == "coffee shop"

    def test_google_forums(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_FORUMS, "forum topic")
        assert p["engine"] == "google_forums"
        assert p["q"] == "forum topic"

    def test_google_ads_text_search(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_ADS, "test company")
        assert p["engine"] == "google_ads_transparency_center"
        assert "q" not in p
        assert p["text"] == "test company"
        assert "advertiser_id" not in p

    def test_google_ads_advertiser_id(self, provider):
        p = provider._build_params(SearchEngineType.GOOGLE_ADS, "AR123456789012")
        assert p["engine"] == "google_ads_transparency_center"
        assert "q" not in p
        assert p["advertiser_id"] == "AR123456789012"
        assert "text" not in p

    def test_google_ads_false_ar_prefix(self, provider):
        """Strings starting with AR but not matching ^AR\\d+$ must use text."""
        p = provider._build_params(SearchEngineType.GOOGLE_ADS, "ART COMPANY")
        assert p["engine"] == "google_ads_transparency_center"
        assert p["text"] == "ART COMPANY"
        assert "advertiser_id" not in p


# ── Source-type mapping tests ─────────────────────────────────────────────────

class TestSourceTypeMapping:
    """Assert _infer_source_type returns the correct SourceType for each engine."""

    def test_search_maps_to_web_page(self):
        assert _infer_source_type(SearchEngineType.GOOGLE_SEARCH) == SourceType.WEB_PAGE

    def test_jobs_maps_to_job_listing(self):
        assert _infer_source_type(SearchEngineType.GOOGLE_JOBS) == SourceType.JOB_LISTING

    def test_news_maps_to_news_article(self):
        assert _infer_source_type(SearchEngineType.GOOGLE_NEWS) == SourceType.NEWS_ARTICLE

    def test_maps_maps_to_business_listing(self):
        assert _infer_source_type(SearchEngineType.GOOGLE_MAPS) == SourceType.BUSINESS_LISTING

    def test_forums_maps_to_forum_post(self):
        assert _infer_source_type(SearchEngineType.GOOGLE_FORUMS) == SourceType.FORUM_POST

    def test_ads_maps_to_advertiser_registry(self):
        """GOOGLE_ADS must classify results as ADVERTISER_REGISTRY, not OFFICIAL_SITE."""
        result = _infer_source_type(SearchEngineType.GOOGLE_ADS)
        assert result == SourceType.ADVERTISER_REGISTRY
        assert result != SourceType.OFFICIAL_SITE


# ── Ads normalization tests ───────────────────────────────────────────────────

class TestAdsNormalization:
    """Test _normalize_ads against the documented SerpApi response schema."""

    def test_single_advertiser_and_creatives(self, provider):
        data = {
            "advertiser": {
                "name": "Mock Advertiser",
                "advertiser_id": "AR123",
                "location": "US",
            },
            "ad_creatives": [
                {"text": "Buy now!", "ad_url": "http://x"},
                {"images": [{"url": "http://img"}], "ad_url": "http://y"},
            ],
        }
        results = provider._normalize_ads(data)
        assert len(results) == 3  # 1 advertiser + 2 creatives

        # Advertiser entry
        assert results[0].title == "Advertiser: Mock Advertiser"
        assert "AR123" in results[0].snippet
        assert results[0].engine == SearchEngineType.GOOGLE_ADS

        # Text creative
        assert "Buy now" in results[1].snippet
        assert results[1].title == "Ad from Mock Advertiser"

        # Image creative
        assert "[Image Ad]" in results[2].snippet
        assert results[2].url == "http://y"

    def test_advertiser_list(self, provider):
        data = {
            "advertisers": [
                {"name": "Acme", "advertiser_id": "AR001", "location": "IN",
                 "link": "https://adstransparency.google.com/advertiser/AR001"},
                {"name": "Beta Corp", "advertiser_id": "AR002", "location": "US", "link": ""},
            ]
        }
        results = provider._normalize_ads(data)
        assert len(results) == 2
        assert results[0].title == "Advertiser: Acme"
        assert "AR001" in results[0].snippet
        assert results[1].title == "Advertiser: Beta Corp"

    def test_empty_response(self, provider):
        assert provider._normalize_ads({}) == []

    def test_all_results_have_ads_engine(self, provider):
        data = {
            "advertisers": [{"name": "X", "advertiser_id": "AR999", "location": ""}]
        }
        for r in provider._normalize_ads(data):
            assert r.engine == SearchEngineType.GOOGLE_ADS


# ── Organic normalization tests ───────────────────────────────────────────────

def test_normalize_organic_empty(provider):
    assert provider._normalize_organic(SearchEngineType.GOOGLE_SEARCH, {}) == []


# ── Error-handling tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_401_raises_serp_api_error(provider):
    """A 401 from SerpApi must raise SerpApiError with 'authentication failed'."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with patch("httpx.AsyncClient.__aenter__", return_value=mock_client):
        with pytest.raises(SerpApiError, match="authentication failed"):
            await provider.search(SearchEngineType.GOOGLE_SEARCH, "test")


# ── UI label test ─────────────────────────────────────────────────────────────

def test_ads_ui_label_in_app():
    """The Streamlit app must display 'Google Ads Transparency Center', not just 'Google Ads'."""
    import os
    app_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "trustlens", "ui", "app.py"
    )
    with open(app_path, encoding="utf-8") as f:
        content = f.read()
    assert "Google Ads Transparency Center" in content, (
        "Expected 'Google Ads Transparency Center' in app.py but it was not found."
    )


# ── Context-extraction limit test ─────────────────────────────────────────────

def test_context_extraction_limit():
    """graph.py must cap single-page extraction at 15000 chars and aggregate at 40000."""
    import os
    graph_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "trustlens", "workflow", "graph.py"
    )
    with open(graph_path, encoding="utf-8") as f:
        code = f.read()
    assert "text[:15000]" in code, "Expected single-page cap of 15000 not found."
    assert "MAX_AGGREGATE_CHARS = 40000" in code, "Expected aggregate bound of 40000 not found."

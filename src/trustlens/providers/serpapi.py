"""
TrustLens SerpApi Provider — Multi-engine search adapter.

Supports 6 SerpApi engines for claim investigation:
- Google Search: General web search
- Google Jobs: Job listing verification
- Google News: Recent news coverage
- Google Maps: Business/location verification
- Google Forums: Community discussions (via google_forums engine)
- Google Ads Transparency Center: Advertiser and ad creative verification
"""

import asyncio
import logging
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

from trustlens.domain.investigation import SearchEngineType

logger = logging.getLogger(__name__)

# Map our enum to SerpApi engine parameter values
_ENGINE_PARAMS: dict[SearchEngineType, str] = {
    SearchEngineType.GOOGLE_SEARCH: "google",
    SearchEngineType.GOOGLE_JOBS: "google_jobs",
    SearchEngineType.GOOGLE_NEWS: "google_news",
    SearchEngineType.GOOGLE_MAPS: "google_maps",
    SearchEngineType.GOOGLE_FORUMS: "google_forums",
    SearchEngineType.GOOGLE_ADS: "google_ads_transparency_center",
}


class SearchResult(BaseModel):
    """A normalized search result from any SerpApi engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    url: str
    snippet: str
    source: str  # Original publisher string
    hostname: str = ""
    publication_date: Optional[str] = None
    engagement_metadata: Optional[str] = None
    engine: SearchEngineType
    position: int
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Original result data for debugging. Not used in logic.",
    )


class SerpApiError(Exception):
    """Raised when SerpApi returns a non-recoverable error."""


class SerpApiProvider:
    """Async SerpApi client supporting multiple Google search engines.

    Each engine has its own parameter mapping and result normalization.
    Includes retry logic for transient failures (timeouts, 5xx).
    """

    BASE_URL = "https://serpapi.com/search.json"
    MAX_RETRIES = 2
    RETRY_DELAY_SECONDS = 1.0

    def __init__(self, api_key: str, timeout_seconds: float = 30.0):
        if not api_key:
            raise ValueError("SerpApi API key is required")
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def search(
        self,
        engine: SearchEngineType,
        query: str,
        *,
        num_results: int = 10,
        location: str | None = None,
        language: str = "en",
        country: str = "us",
    ) -> list[SearchResult]:
        """Execute a search on the specified engine and return normalized results.

        Args:
            engine: Which SerpApi engine to use.
            query: The search query string.
            num_results: Maximum results to request (where applicable).
            location: Location context (for Jobs, Maps).
            language: Language code (hl parameter).
            country: Country code (gl parameter).

        Returns:
            List of normalized SearchResult objects.

        Raises:
            SerpApiError: On authentication or non-recoverable errors.
        """
        logger.info(f"SerpApi search: engine={engine.value}, query='{query}'")
        params = self._build_params(
            engine, query,
            num_results=num_results,
            location=location,
            language=language,
            country=country,
        )

        data = await self._execute_with_retry(params)
        results = self._normalize_results(engine, data)
        logger.info(
            f"SerpApi returned {len(results)} results for "
            f"'{query}' on {engine.value}"
        )
        return results

    def _build_params(
        self,
        engine: SearchEngineType,
        query: str,
        *,
        num_results: int = 10,
        location: str | None = None,
        language: str = "en",
        country: str = "us",
    ) -> dict[str, Any]:
        """Build SerpApi request parameters for the given engine."""
        params: dict[str, Any] = {
            "api_key": self._api_key,
            "output": "json",
            "q": query,
            "engine": _ENGINE_PARAMS[engine],
        }

        if engine == SearchEngineType.GOOGLE_SEARCH:
            params["num"] = num_results
            params["hl"] = language
            params["gl"] = country

        elif engine == SearchEngineType.GOOGLE_JOBS:
            if location:
                params["location"] = location

        elif engine == SearchEngineType.GOOGLE_NEWS:
            params["hl"] = language
            params["gl"] = country

        elif engine == SearchEngineType.GOOGLE_MAPS:
            if location:
                params["ll"] = location  # lat,lng format

        elif engine == SearchEngineType.GOOGLE_FORUMS:
            params.pop("num", None) # Google Forums API uses num in a similar way, but let's just stick to base q

        elif engine == SearchEngineType.GOOGLE_ADS:
            params.pop("q", None)
            import re
            if re.match(r'^AR\d+$', query):
                params["advertiser_id"] = query
            else:
                params["text"] = query

        return params

    async def _execute_with_retry(self, params: dict[str, Any]) -> dict:
        """Execute HTTP request with retry logic for transient failures."""
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self.BASE_URL, params=params)

                    if response.status_code in (401, 403):
                        raise SerpApiError(
                            f"SerpApi authentication failed (HTTP {response.status_code}). "
                            "Check your SERPAPI_API_KEY."
                        )

                    if response.status_code == 429:
                        body = response.json() if response.content else {}
                        if "activate" in str(body).lower():
                            raise SerpApiError(
                                "SerpApi account requires email activation. "
                                "Check your SerpApi dashboard."
                            )
                        raise SerpApiError(
                            "SerpApi rate limit exceeded. Try again later."
                        )

                    response.raise_for_status()
                    return response.json()

            except SerpApiError:
                raise  # Don't retry auth/rate-limit errors

            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError):
                    # Don't retry 4xx errors (except 408, 429 handled above)
                    if 400 <= exc.response.status_code < 500:
                        raise
                logger.warning(
                    f"SerpApi attempt {attempt + 1}/{self.MAX_RETRIES} failed: {exc}"
                )
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                    await asyncio.sleep(delay)

        raise SerpApiError(
            f"SerpApi search failed after {self.MAX_RETRIES} attempts: {last_error}"
        )

    def _normalize_results(
        self, engine: SearchEngineType, data: dict
    ) -> list[SearchResult]:
        """Normalize raw SerpApi response into SearchResult objects."""
        if engine in (SearchEngineType.GOOGLE_SEARCH, SearchEngineType.GOOGLE_FORUMS):
            return self._normalize_organic(engine, data)
        elif engine == SearchEngineType.GOOGLE_NEWS:
            return self._normalize_news(data)
        elif engine == SearchEngineType.GOOGLE_JOBS:
            return self._normalize_jobs(data)
        elif engine == SearchEngineType.GOOGLE_MAPS:
            return self._normalize_maps(data)
        elif engine == SearchEngineType.GOOGLE_ADS:
            return self._normalize_ads(data)
        return []

    def _normalize_organic(
        self, engine: SearchEngineType, data: dict
    ) -> list[SearchResult]:
        """Normalize Google organic / forum discussion results."""
        from urllib.parse import urlparse
        import json
        
        results = []
        for idx, item in enumerate(data.get("organic_results", [])):
            url = item.get("link", "")
            hostname = urlparse(url).netloc if url else ""
            
            engagement = None
            rich = item.get("rich_snippet", {})
            if isinstance(rich, dict) and "top" in rich:
                engagement = json.dumps(rich["top"])
            
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("snippet", ""),
                source=item.get("displayed_link", item.get("source", "")),
                hostname=hostname,
                publication_date=item.get("date"),
                engagement_metadata=engagement,
                engine=engine,
                position=idx + 1,
                raw_data=item,
            ))
        return results

    def _normalize_news(self, data: dict) -> list[SearchResult]:
        """Normalize Google News results."""
        from urllib.parse import urlparse
        
        results = []
        for idx, item in enumerate(data.get("news_results", [])):
            source_info = item.get("source", {})
            source_name = (
                source_info.get("name", "")
                if isinstance(source_info, dict)
                else str(source_info)
            )
            url = item.get("link", "")
            hostname = urlparse(url).netloc if url else ""
            
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("snippet", ""),
                source=source_name,
                hostname=hostname,
                publication_date=item.get("date"),
                engine=SearchEngineType.GOOGLE_NEWS,
                position=idx + 1,
                raw_data=item,
            ))
        return results

    def _normalize_jobs(self, data: dict) -> list[SearchResult]:
        """Normalize Google Jobs results."""
        from urllib.parse import urlparse
        
        results = []
        for idx, item in enumerate(data.get("jobs_results", [])):
            # Google Jobs results have different structure
            description = item.get("description", "")
            snippet = description[:300] + "..." if len(description) > 300 else description

            # Build URL from share_link or detected_extensions
            url = item.get("share_link", item.get("related_links", [{}])[0].get("link", "")) if item.get("related_links") else item.get("share_link", "")
            hostname = urlparse(url).netloc if url else ""
            
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url or "",
                snippet=snippet,
                source=item.get("company_name", ""),
                hostname=hostname,
                publication_date=item.get("detected_extensions", {}).get("posted_at"),
                engine=SearchEngineType.GOOGLE_JOBS,
                position=idx + 1,
                raw_data=item,
            ))
        return results

    def _normalize_maps(self, data: dict) -> list[SearchResult]:
        """Normalize Google Maps / local results."""
        import json
        from urllib.parse import urlparse
        
        results = []
        for idx, item in enumerate(data.get("local_results", [])):
            # Maps results may have address, rating, etc.
            address = item.get("address", "")
            rating = item.get("rating")
            reviews = item.get("reviews")

            snippet_parts = []
            if address:
                snippet_parts.append(f"Address: {address}")
            if rating:
                snippet_parts.append(f"Rating: {rating}")
            if reviews:
                snippet_parts.append(f"Reviews: {reviews}")
            snippet = " | ".join(snippet_parts) if snippet_parts else item.get("description", "")

            url = item.get("website", item.get("place_id_search", ""))
            hostname = urlparse(url).netloc if url else ""
            
            engagement = None
            if rating or reviews:
                engagement = json.dumps({"rating": rating, "reviews": reviews})

            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=snippet,
                source=item.get("type", "Google Maps"),
                hostname=hostname,
                engagement_metadata=engagement,
                engine=SearchEngineType.GOOGLE_MAPS,
                position=idx + 1,
                raw_data=item,
            ))
        return results

    def _normalize_ads(self, data: dict) -> list[SearchResult]:
        """Normalize Google Ads Transparency Center results."""
        results = []
        
        # If searching by text, it might return a list of advertisers
        for idx, item in enumerate(data.get("advertisers", [])):
            name = item.get("name", "")
            adv_id = item.get("advertiser_id", "")
            location = item.get("location", "")
            snippet = f"Advertiser: {name} | ID: {adv_id} | Location: {location}"
            results.append(SearchResult(
                title=f"Advertiser: {name}",
                url=item.get("link", ""),
                snippet=snippet,
                source="Google Ads Transparency Center",
                hostname="adstransparency.google.com",
                engine=SearchEngineType.GOOGLE_ADS,
                position=idx + 1,
                raw_data=item,
            ))
            
        # Single advertiser (when searched by ID)
        single_adv = data.get("advertiser")
        if single_adv and isinstance(single_adv, dict):
            name = single_adv.get("name", "")
            adv_id = single_adv.get("advertiser_id", "")
            location = single_adv.get("location", "")
            snippet = f"Advertiser Details: {name} | ID: {adv_id} | Location: {location}"
            results.append(SearchResult(
                title=f"Advertiser: {name}",
                url=single_adv.get("link", ""),
                snippet=snippet,
                source="Google Ads Transparency Center",
                hostname="adstransparency.google.com",
                engine=SearchEngineType.GOOGLE_ADS,
                position=len(results) + 1,
                raw_data=single_adv,
            ))
            
        # ad_creatives (when searched by ID)
        for idx, item in enumerate(data.get("ad_creatives", [])):
            name = single_adv.get("name", "") if isinstance(single_adv, dict) else ""
            snippet_text = item.get("text", "")
            
            if not snippet_text:
                if item.get("videos"):
                    snippet_text = "[Video Ad]"
                elif item.get("images"):
                    snippet_text = "[Image Ad]"
                else:
                    snippet_text = "[Ad]"
            
            snippet = f"Ad by {name}: {snippet_text}"
            results.append(SearchResult(
                title=f"Ad from {name}",
                url=item.get("ad_url", ""),
                snippet=snippet,
                source="Google Ads Transparency Center",
                hostname="adstransparency.google.com",
                engine=SearchEngineType.GOOGLE_ADS,
                position=len(results) + idx + 1,
                raw_data=item,
            ))
            
        return results

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import logging

logger = logging.getLogger(__name__)

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', '_ga', 'mc_cid', 'mc_eid'
}

def normalize_url(url: str) -> str:
    """Removes tracking parameters and normalizes the URL."""
    if not url:
        return url
        
    try:
        parsed = urlparse(url)
        
        # Remove tracking queries
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        filtered_query = {
            k: v for k, v in query_params.items() 
            if k.lower() not in TRACKING_PARAMS
        }
        
        # Reconstruct URL
        new_query = urlencode(filtered_query, doseq=True)
        normalized_parsed = parsed._replace(query=new_query)
        
        # Lowercase scheme and netloc for normalization
        normalized_parsed = normalized_parsed._replace(
            scheme=normalized_parsed.scheme.lower(),
            netloc=normalized_parsed.netloc.lower()
        )
        
        return urlunparse(normalized_parsed)
    except Exception as e:
        logger.warning(f"Failed to normalize URL {url}: {str(e)}")
        return url

def normalize_domain(domain: str) -> str:
    """Strips www. from domains for normalization."""
    if not domain:
        return domain
    domain = domain.lower()
    if domain.startswith('www.'):
        return domain[4:]
    return domain

def deduplicate_results(results: list) -> list:
    """Deduplicates search results by normalized URL."""
    seen_urls = set()
    unique_results = []
    
    for result in results:
        # Assuming result has a 'url' attribute
        # Need to handle both dict and Pydantic object for flexibility
        url = getattr(result, 'url', None) or (isinstance(result, dict) and result.get('url'))
        
        if not url:
            # If no URL, keep it, could be a special result type
            unique_results.append(result)
            continue
            
        norm_url = normalize_url(url)
        if norm_url not in seen_urls:
            seen_urls.add(norm_url)
            
            # Optionally normalize the domain in the source if applicable
            # We don't mutate the frozen pydantic object here though, 
            # so we just keep the first unique instance.
            
            unique_results.append(result)
            
    return unique_results

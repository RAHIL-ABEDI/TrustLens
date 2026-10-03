import pytest
from unittest.mock import patch
from trustlens.workflow.graph import understand_claim

@pytest.mark.asyncio
async def test_understand_claim_extraction_limit():
    """Test that understand_claim correctly extracts up to 15,000 characters."""
    
    # Create a dummy HTML payload that's very long
    # Use repeating blocks so we can check what is retained.
    block = "This is a test block of text. " * 10  # ~300 chars
    html_content = "<html><body>" + (block * 100) + "</body></html>" # ~30,000 chars
    
    # Insert a marker at the 5000 character mark to ensure it's retained
    # and a marker at the 25000 character mark to ensure it's excluded.
    # We'll just generate a 30,000 char plain string for the mock.
    
    long_text = "A" * 5000 + "MARKER_AT_5000" + "B" * 9986 + "MARKER_AT_15000" + "C" * 10000 + "MARKER_AT_25000"
    # Total length: 5000 + 14 + 9986 + 15 + 10000 + 15 = 25030 chars
    
    with patch("trustlens.workflow.graph._fetch_url_text") as mock_fetch:
        mock_fetch.return_value = long_text
        
        state = {"original_claim": "Check this url https://example.com"}
        
        result = await understand_claim(state)
        
        assert "raw_search_results" in result
        raw_results = result["raw_search_results"]
        assert len(raw_results) == 1
        
        snippet = raw_results[0]["snippet"]
        
        # Check length is exactly 15000
        assert len(snippet) == 15000
        
        # Check that the 5000 marker is retained (proves we didn't stop at 4000)
        assert "MARKER_AT_5000" in snippet
        
        # Check that the 25000 marker is excluded
        assert "MARKER_AT_25000" not in snippet

# TrustLens — Multi-Source Digital Trust Investigator

**Track:** Knowledge & Public Interest  
**Hackathon:** SerpApi India Hackathon 2026

## What it does
TrustLens is a tool for investigating online claims—such as job offers, company claims, product features, and online offers. Instead of trying to calculate a generic "scam score," TrustLens gathers transparent, multi-source evidence using SerpApi to present the facts to the user.

## SerpApi Integration
TrustLens makes core use of SerpApi to investigate claims, leveraging 6 distinct search engines:
- **Google Search**: General factual cross-referencing.
- **Google Jobs**: Verifying job offer claims.
- **Google News**: Checking recent news and announcements.
- **Google Maps**: Validating physical locations and businesses.
- **Google Forums**: Gathering community discussions and experiences.
- **Google Ads Transparency Center**: Checking advertiser identity and active ad campaigns.

## Architecture
TrustLens is built with Python 3.11+, using Pydantic v2 for data validation, LangGraph for the workflow and investigation orchestration, and Streamlit for the user interface. It uses the `gemini-3.5-flash-lite` model via the `google-genai` SDK for language processing.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -e .
   ```
2. Set up environment:
   ```bash
   cp .env.example .env
   # Edit .env with your SERPAPI_API_KEY and GEMINI_API_KEY
   ```
3. Run the application:
   ```bash
   streamlit run src/trustlens/ui/app.py
   ```

## AI Tools Disclosure
This project was developed with assistance from Antigravity/Claude for code generation and architecture discussions.

## License
MIT License

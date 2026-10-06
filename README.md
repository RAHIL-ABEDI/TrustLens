# 🔍 TrustLens

> **Investigate digital claims with traceable evidence, not opaque scores.**

In an era of online misinformation, generic "scam percentages" are entirely useless because they lack context, transparency, and proof. TrustLens is an autonomous AI investigator that breaks down complex online claims (job offers, product guarantees, company policies) and cross-references them against live, multi-source evidence to provide nuanced, verifiable findings.

---

## 🧠 The "6-Engine" SerpApi Strategy

Our killer feature isn't just searching the web—it's **intelligent, dynamic engine routing**. Depending on the nature of the claim, our LangGraph orchestrator dynamically selects from 6 distinct SerpApi engines to build a comprehensive, bulletproof evidence map:

* **🔍 Google Search:** Factual baseline cross-referencing and official documentation.
* **💼 Google Jobs:** Verifying job offer legitimacy and historical posting consistency.
* **📰 Google News:** Fact-checking corporate announcements, PR, and recent press.
* **📍 Google Maps:** Validating physical entity existence and address reputation.
* **💬 Google Forums:** Extracting real user experiences, warnings, and community sentiment.
* **📢 Google Ads Transparency Center:** Tracing advertiser identity and active campaign tracking.

---

## 🏗️ Architecture

TrustLens is powered by a robust, multi-agent workflow designed for accuracy and determinism:

1. **Decomposition:** A Gemini 3.5 Flash-Lite LLM breaks down complex user claims into verifiable atomic sub-claims.
2. **Execution:** The `LangGraph` planner routes queries to the optimal SerpApi engines.
3. **Normalization & Mapping:** Evidence is collected, normalized, and mapped against the atomic claims using strictly typed `Pydantic v2` domain models.
4. **Synthesis:** Findings are generated with explicit *Supporting*, *Contradicting*, or *Neutral* stances.
5. **Presentation:** A premium, glass-morphic `Streamlit` dashboard presents the investigation clearly to the user.

---

## ⚡ Zero-to-Running in 60 Seconds

We value the judges' time. Getting TrustLens running locally is completely frictionless.

**1. Clone & Install**
```bash
git clone https://github.com/yourusername/trustlens.git
cd trustlens
pip install -e .
```

**2. Configure Credentials**
```bash
cp .env.example .env
```
*Open `.env` and add your `SERPAPI_API_KEY` and `GEMINI_API_KEY`.*

**3. Launch the Investigator**
```bash
streamlit run src/trustlens/ui/app.py
```
*The app will instantly launch on `http://localhost:8501` (or the next available port).*

---

## 🤖 AI Tools Disclosure

This project was developed with the assistance of AI pair-programming tools. Architecture brainstorming, component generation, and iterative debugging were accelerated using **Google Antigravity** and **Claude**. All resulting business logic, SerpApi integrations, and domain models were rigorously tested and manually curated for this hackathon.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

"""
Weekly viAct Market Radar — headless pipeline for GitHub Actions.

Flow:
  Agent 1 (Tavily)   → discover top 3 content gaps
  Agent 2 (Firecrawl)→ scrape competitor pages for each gap
  Agent 3 (Groq)     → generate full webpage content suite
  push_to_sheets     → append rows to Google Sheets (service account, no login)

Required env vars (set as GitHub Secrets):
  TAVILY_API_KEY, GROQ_API_KEY, FIRECRAWL_API_KEY, GCP_SERVICE_ACCOUNT, SHEET_ID
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from agent1_market_explorer import discover_market_gaps
from agent2_data_extractor import extract_competitor_content
from agent3_content_architect import generate_structured_content
from push_to_sheets import push_webpage
from research_competitors import scrape_viact_sitemap


def log(msg: str):
    print(f"[radar] {msg}", flush=True)


def main():
    log("=== viAct Weekly Market Radar — Auto Run ===")

    # ── Step 1: Agent 1 — discover gaps ───────────────────────────────────────
    log("Step 1: Agent 1 scanning competitors via Tavily...")
    radar = discover_market_gaps()
    gaps = radar.get("topics", [])
    viact_pages = radar.get("viact_known_pages", [])

    if not gaps:
        log("No confirmed gaps found. Check TAVILY_API_KEY and competitor list. Exiting.")
        sys.exit(1)

    log(f"Found {len(gaps)} gap(s): {[g['topic'] for g in gaps]}")

    # ── Process top 1 gap per weekly run (stay within free API limits) ─────────
    # Change gaps[:1] to gaps[:3] to process all 3 if API quotas allow
    autorun_base = int(os.getenv("GITHUB_RUN_NUMBER", "1"))

    for i, gap in enumerate(gaps[:1], 1):
        topic = gap["topic"]
        log(f"\n--- Gap {i}: '{topic}' ---")

        # ── Step 2: Agent 2 — scrape competitor evidence pages ────────────────
        evidence_urls = [
            e["url"] for e in gap.get("competitor_evidence", []) if e.get("url")
        ]
        log(f"Step 2: Agent 2 scraping {len(evidence_urls)} competitor URL(s) via Firecrawl...")
        competitor_data = extract_competitor_content(evidence_urls) if evidence_urls else {}
        accessible = sum(1 for r in competitor_data.values() if r.get("success"))
        log(f"  {accessible}/{len(evidence_urls)} pages accessible.")

        # ── Step 3: Agent 3 — generate content ────────────────────────────────
        log("Step 3: Agent 3 generating content suite via Groq/Llama...")
        try:
            content = generate_structured_content(
                topic=topic,
                competitor_data=competitor_data,
                viact_pages=viact_pages,
                references="",
                radar_topic_entry=gap,
            )
        except Exception as exc:
            log(f"  Agent 3 failed: {exc}")
            continue

        # ── Step 4: Push to Google Sheets ──────────────────────────────────────
        log("Step 4: Pushing to Google Sheets...")
        try:
            count = push_webpage(
                content=content,
                decision_logic=content.get("decision_logic", ""),
                input_source=f"Weekly Auto-Run #{autorun_base + i - 1}",
                competitor_urls=list(competitor_data.keys()),
                autorun_num=autorun_base + i - 1,
                unverified=True,
            )
            log(f"  Pushed {count} row(s) to Google Sheets. Topic: '{topic}'")
        except Exception as exc:
            log(f"  Sheets push failed: {exc}")
            # Dump content locally as fallback
            out_path = f".tmp/weekly_gap_{i}.json"
            os.makedirs(".tmp", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            log(f"  Saved fallback to {out_path}")

    log("\n=== Weekly Radar Complete ===")


if __name__ == "__main__":
    main()

"""
daily_full_pipeline.py — Daily full content automation pipeline.

Runs every day via GitHub Actions. Does 3 things:
  1. Competitor intel scan → finds 5 content topics (Pillar, Blog, Industry, CS, VA)
  2. Pushes intel + topics to Google Sheets
  3. Runs each of the 5 agents with today's topic → saves pages to Sheets

Why this exists:
  Market Radar (weekly_scan_script.py) finds competitor-driven gaps.
  This pipeline handles intelligence-driven daily content — faster, topic-guided.

Agents used:
  - Pillar + Blog  → agent3_content_architect.generate_structured_content
  - Industry page  → agent3_content_architect.generate_industry_page
  - Case Study     → agent6_case_study_builder.generate_case_study
  - VA page        → agent7_video_analytics_page.generate_va_page
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))


def log(msg: str):
    print(f"[daily] {msg}", flush=True)


# ── Step 1: Run competitor intel scan + generate 5 topics ─────────────────────

def run_intel_scan() -> dict:
    log("=== Step 1: Competitor Intel Scan ===")
    from competitor_news_monitor import run_daily_monitor
    result = run_daily_monitor(
        progress_callback=lambda phase, msg: log(f"  {msg}")
    )
    log(f"  Intel scan complete — urgency: {result.get('urgency', '?').upper()}")
    log(f"  Competitor news: {result.get('counts', {}).get('competitor_news', 0)}")
    log(f"  Trends: {result.get('counts', {}).get('trends', 0)}")
    return result


# ── Step 2: Push intel + topics to Sheets ─────────────────────────────────────

def push_intel_to_sheets(intel: dict):
    log("=== Step 2: Pushing intel + topics to Sheets ===")
    from push_to_sheets import (
        push_competitor_intel,
        push_daily_topics,
        push_product_launches,
        push_competitor_site_changes,
    )

    try:
        push_competitor_intel(intel)
        log("  Competitor Intel tab: pushed")
    except Exception as e:
        log(f"  Competitor Intel push failed: {e}")

    try:
        push_daily_topics(intel)
        log("  Daily Topics tab: pushed")
    except Exception as e:
        log(f"  Daily Topics push failed: {e}")

    try:
        count = push_product_launches(intel)
        log(f"  Product Launches tab: {count} row(s)")
    except Exception as e:
        log(f"  Product Launches push failed: {e}")

    try:
        count = push_competitor_site_changes(intel)
        log(f"  Competitor Site Changes tab: {count} row(s)")
    except Exception as e:
        log(f"  Competitor Site Changes push failed: {e}")


# ── Step 3: Run all 5 agents ───────────────────────────────────────────────────

def run_pillar_agent(topic_obj: dict) -> bool:
    """Generate a pillar page from the daily pillar topic."""
    topic = topic_obj.get("topic", "")
    keyword = topic_obj.get("primary_keyword", "")
    why = topic_obj.get("why", "")

    if not topic:
        log("  Pillar: no topic — skipping.")
        return False

    log(f"  Pillar topic: '{topic}'")
    try:
        from agent3_content_architect import generate_structured_content
        from push_to_sheets import push_webpage_vertical

        content = generate_structured_content(
            topic=topic,
            competitor_data={},
            viact_pages=[],
            references="",
            radar_topic_entry={
                "topic": topic,
                "competitor_evidence": [],
                "opportunity_score": "High",
                "competitor_count": 0,
                "viact_search_query": keyword or topic,
                "why_trending": why,
                "pillar_topic": topic,
            },
        )
        push_webpage_vertical(
            content=content,
            decision_logic=content.get("decision_logic", why),
            input_source="Daily Auto-Run — Pillar",
            unverified=True,
        )
        log(f"  Pillar page saved to Sheets: '{topic}'")
        return True
    except Exception as e:
        log(f"  Pillar agent failed: {e}")
        return False


def run_blog_agent(topic_obj: dict) -> bool:
    """Generate a blog post from the daily blog topic."""
    topic = topic_obj.get("topic", "")
    keyword = topic_obj.get("primary_keyword", "")
    why = topic_obj.get("why", "")

    if not topic:
        log("  Blog: no topic — skipping.")
        return False

    log(f"  Blog topic: '{topic}'")
    try:
        from agent3_content_architect import generate_structured_content
        from push_to_sheets import push_webpage_vertical

        content = generate_structured_content(
            topic=topic,
            competitor_data={},
            viact_pages=[],
            references="",
            radar_topic_entry={
                "topic": topic,
                "competitor_evidence": [],
                "opportunity_score": "Medium",
                "competitor_count": 0,
                "viact_search_query": keyword or topic,
                "why_trending": why,
                "pillar_topic": topic,
            },
            content_type="blog",
        )
        push_webpage_vertical(
            content=content,
            decision_logic=content.get("decision_logic", why),
            input_source="Daily Auto-Run — Blog",
            unverified=True,
        )
        log(f"  Blog post saved to Sheets: '{topic}'")
        return True
    except Exception as e:
        log(f"  Blog agent failed: {e}")
        return False


def run_industry_agent(topic_obj: dict) -> bool:
    """Generate an industry page from the daily industry topic."""
    industry = topic_obj.get("industry", "")
    topic = topic_obj.get("topic", "")
    why = topic_obj.get("why", "")

    if not industry:
        log("  Industry: no industry — skipping.")
        return False

    log(f"  Industry: '{industry}' — topic: '{topic}'")
    try:
        from agent3_content_architect import generate_industry_page
        from agent2_data_extractor import extract_competitor_content
        from push_to_sheets import push_industry_page_vertical

        industry_slug = industry.lower().replace(" ", "-").replace("&", "and").replace("/", "-")

        # Try to scrape viact.ai reference for tone
        viact_md = ""
        try:
            viact_url = f"https://www.viact.ai/{industry_slug}"
            scraped = extract_competitor_content([viact_url])
            viact_md = scraped.get(viact_url, {}).get("markdown", "")
        except Exception:
            pass

        result = generate_industry_page(
            industry_name=industry,
            industry_slug=industry_slug,
            viact_page_content=viact_md,
            competitor_content={},
            references="",
            viact_pages=[],
            custom_instructions=f"Focus topic: {topic}. Context: {why}" if topic else "",
        )

        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or os.getenv("SHEET_ID", "")
        push_industry_page_vertical(content=result, industry_name=industry, sheet_id=sheet_id)
        log(f"  Industry page saved to Sheets: '{industry}'")
        return True
    except Exception as e:
        log(f"  Industry agent failed: {e}")
        return False


def run_case_study_agent(topic_obj: dict) -> bool:
    """Generate a case study from the daily CS topic."""
    company_type = topic_obj.get("company_type", "")
    industry = topic_obj.get("industry", "Construction")
    location = topic_obj.get("location", "Singapore")
    detection_focus = topic_obj.get("detection_focus", "")
    why = topic_obj.get("why", "")

    if not company_type:
        log("  Case Study: no company_type — skipping.")
        return False

    # Use a representative company name based on the type
    company_display = f"{company_type} ({location})"
    log(f"  Case Study: '{company_display}' — {detection_focus}")

    try:
        from agent6_case_study_builder import generate_case_study
        from push_to_sheets import push_case_study

        result = generate_case_study(
            company=company_display,
            industry=industry,
            location=location,
            products_used=[],
            references="",
            custom_instructions=(
                f"This is a template case study representing a typical {company_type}. "
                f"Focus on {detection_focus} deployment. Context: {why}. "
                "Use realistic placeholder metrics in [brackets] where real data is unavailable."
            ),
            run_tavily=True,
        )

        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or os.getenv("SHEET_ID", "")
        push_case_study(result=result, sheet_id=sheet_id)
        log(f"  Case study saved to Sheets: '{company_display}'")
        return True
    except Exception as e:
        log(f"  Case Study agent failed: {e}")
        return False


def run_va_agent(topic_obj: dict) -> bool:
    """Generate a VA item page from the daily VA detection topic."""
    detection_name = topic_obj.get("detection_name", "")
    why = topic_obj.get("why", "")

    if not detection_name:
        log("  VA: no detection_name — skipping.")
        return False

    log(f"  VA detection: '{detection_name}'")
    try:
        from agent7_video_analytics_page import generate_va_page
        from push_to_sheets import push_video_analytics_page

        result = generate_va_page(
            detection_name=detection_name,
            run_tavily=True,
            progress_callback=lambda msg: log(f"    {msg}"),
        )

        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or os.getenv("SHEET_ID", "")
        push_video_analytics_page(result=result, sheet_id=sheet_id)
        log(f"  VA page saved to Sheets: '{detection_name}'")
        return True
    except Exception as e:
        log(f"  VA agent failed: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log("=== Daily Full Pipeline — viAct Content Automation ===")

    # Step 1 — Intel scan
    intel = run_intel_scan()
    topics = intel.get("daily_topics", {})

    # Step 2 — Push to Sheets
    push_intel_to_sheets(intel)

    # Step 3 — Run all 5 agents
    log("=== Step 3: Running all 5 content agents ===")

    results = {
        "pillar":   run_pillar_agent(topics.get("pillar_topic", {})),
        "blog":     run_blog_agent(topics.get("blog_topic", {})),
        "industry": run_industry_agent(topics.get("industry_topic", {})),
        "cs":       run_case_study_agent(topics.get("case_study_topic", {})),
        "va":       run_va_agent(topics.get("va_topic", {})),
    }

    succeeded = sum(1 for v in results.values() if v)
    failed    = sum(1 for v in results.values() if not v)

    log(f"\n=== Pipeline Complete — {succeeded}/5 agents succeeded, {failed} failed ===")
    for name, ok in results.items():
        status = "OK" if ok else "FAILED/SKIPPED"
        log(f"  {name:12} {status}")


if __name__ == "__main__":
    main()

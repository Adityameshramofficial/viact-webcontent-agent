"""
viact.ai content generation pipeline.

Social mode (default):
  python run_pipeline.py --url https://viact.ai
  python run_pipeline.py --brief "viact.ai PPE detection AI"
  python run_pipeline.py --file path/to/doc.pdf

Webpage mode (Manager-Ready, with HITL gates):
  python run_pipeline.py --mode webpage --brief "Fall Prevention in High-Rise Construction"
  python run_pipeline.py --mode webpage --url https://viact.ai/case-study --autorun 7
  python run_pipeline.py --mode webpage --brief "PPE Compliance" --competitors "https://url1.com,https://url2.com"
"""
import argparse
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from scrape_url import scrape
from parse_doc import parse
from generate_content import generate
from generate_image import generate_image
from push_to_sheets import push, push_webpage

SHEET_ID_LINK = "https://docs.google.com/spreadsheets/d/1G_OAdhKc92DRQOLjBCFP_cE3AiQoGQLa9bsR-ZnpkKE"


def _resolve_brief(args) -> tuple[str, str]:
    """Return (brief_text, source_label) from --url / --brief / --file."""
    if args.url:
        print(f"[Input] Scraping {args.url} ...")
        data = scrape(args.url)
        return data["title"] + ". " + data["body"], args.url
    if args.file:
        print(f"[Input] Parsing {args.file} ...")
        data = parse(args.file)
        return data["text"], os.path.basename(args.file)
    print("[Input] Using provided brief ...")
    return args.brief, "topic brief"


# ---------------------------------------------------------------------------
# Social pipeline (unchanged)
# ---------------------------------------------------------------------------
def run_social(args):
    brief, source_label = _resolve_brief(args)
    print(f"       Brief length: {len(brief)} chars")

    print("[2/4] Generating content with Gemini (free tier) ...")
    content = generate(brief)
    print("      Content generated for: LinkedIn, Twitter, Instagram, Blog")

    print("[3/4] Refining image prompt via Nano Banana Pro ...")
    image_url = ""
    try:
        img_result = generate_image(content.get("image_prompt", brief[:200]))
        image_url = img_result.get("image_url", "")
        if img_result.get("warning"):
            print(f"      Skipped ({img_result['warning'][:80]})")
        elif img_result.get("model"):
            print(f"      Prompt refined by {img_result['model']}")
    except Exception as e:
        print(f"      Skipped ({e})")

    print("[4/4] Writing rows to Google Sheets ...")
    rows_written = push(content, input_source=source_label, image_url=image_url)
    print(f"      {rows_written} rows written.")

    print()
    print("Done!")
    print(f"View your content: {SHEET_ID_LINK}")
    print()
    print("── Preview ─────────────────────────────────────────────────────")
    print(f"LinkedIn : {content['linkedin']['copy'][:120]}...")
    print(f"Twitter  : {content['twitter']['copy']}")
    print(f"Blog     : {content['blog']['title']}")


# ---------------------------------------------------------------------------
# Webpage pipeline — 4-phase sequential research + HITL gates
# ---------------------------------------------------------------------------
def run_webpage(args):
    from research_competitors import (
        research_competitors,
        build_gap_table,
        match_category,
        COMPETITOR_MAP,
    )
    from generate_webpage_content import generate_webpage, build_decision_logic

    topic, source_label = _resolve_brief(args)
    topic = topic[:500]  # keep topic concise

    print()
    print("══════════════════════════════════════════════════════════════════")
    print("  viAct Strategic Content Architect — Manager-Ready Webpage Mode ")
    print("══════════════════════════════════════════════════════════════════")

    # ── HITL Gate 1: Competitor Selection ─────────────────────────────────────
    category_key = match_category(topic)
    category = COMPETITOR_MAP[category_key]
    default_competitors = category["competitors"]

    print()
    print(f"── PHASE 1: Competitor Discovery ─────────────────────────────────")
    print(f"   Topic category: '{category['label']}'")
    print()
    for i, c in enumerate(default_competitors, 1):
        print(f"   {i}. {c['name']}")
        print(f"      {c['url']}")
    print(f"   {len(default_competitors) + 1}. Analyze ALL (recommended)")
    print()

    if args.competitors:
        # Non-interactive: use supplied URLs
        competitor_urls = [u.strip() for u in args.competitors.split(",") if u.strip()]
        print(f"   Using supplied competitors: {', '.join(competitor_urls)}")
    else:
        raw = input("   Which competitor? (enter number, or press Enter for ALL): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(default_competitors):
            chosen = default_competitors[int(raw) - 1]
            competitor_urls = [chosen["url"]]
            print(f"   Selected: {chosen['name']}")
        else:
            competitor_urls = None
            print("   Analyzing ALL competitors.")

    # ── 4-Phase Research ───────────────────────────────────────────────────────
    print()

    def cli_progress(phase: int, message: str):
        prefix = {1: "PHASE 1", 2: "PHASE 2", 3: "PHASE 3", 4: "PHASE 4"}.get(phase, f"PHASE {phase}")
        print(f"   [{prefix}] {message}")

    research = research_competitors(
        topic,
        competitor_urls,
        progress_callback=cli_progress,
    )

    # ── HITL Gate 2: Gap Selection ─────────────────────────────────────────────
    print()
    print("── GAP ANALYSIS TABLE ────────────────────────────────────────────")
    rows = build_gap_table(research)
    col_w = 28
    header = f"{'Competitor':<{col_w}} {'Depth':<8} {'Regulatory':<14} {'Gap Type':<16} Notable Absence"
    print(f"   {header}")
    print("   " + "─" * 90)
    for r in rows:
        print(
            f"   {r['Competitor']:<{col_w}} "
            f"{r['Content Depth']:<8} "
            f"{r['Regulatory Context']:<14} "
            f"{r['Gap Type']:<16} "
            f"{r['Notable Absence'][:40]}"
        )

    print()
    gaps = research.get("identified_gaps", [])
    print("── IDENTIFIED GAPS (universal — absent from ALL competitors) ─────")
    for i, g in enumerate(gaps, 1):
        print(f"   {i}. {g}")
    print(f"   {len(gaps) + 1}. Let the AI choose the best angle")
    print()

    raw_gap = input("   Which gap should I build into a page? (enter number): ").strip()
    if raw_gap.isdigit() and 1 <= int(raw_gap) <= len(gaps):
        selected_gap = gaps[int(raw_gap) - 1]
        print(f"   Selected: {selected_gap[:80]}...")
    else:
        selected_gap = gaps[0] if gaps else ""
        print("   Using the top-priority gap.")

    # ── HITL Gate 3: Reference Collection ─────────────────────────────────────
    print()
    print("── PHASE 3: Reference Collection ────────────────────────────────")
    print("   Provide reference links, PDFs, or case study data for accuracy.")
    print("   Press Enter to use public MOM/BCA data (content will be [Unverified]).")
    print()
    references = input("   Reference material (URL / text / Enter to skip): ").strip()
    unverified = not bool(references)
    if unverified:
        print("   No reference provided — using public MOM/BCA data. Output marked [Unverified].")
    else:
        print(f"   Reference accepted: {references[:60]}...")

    # ── Phase 4: Content Generation ───────────────────────────────────────────
    print()
    print("── PHASE 4: Generating Content Suite ────────────────────────────")
    print("   Running Gemini 2.5 Flash — 6-output package ...")

    content = generate_webpage(
        topic=topic,
        gap_brief=research.get("gap_brief", ""),
        identified_gaps=research.get("identified_gaps", []),
        keyword_signal=research.get("keyword_signal", ""),
        references=references,
        viact_pages=research.get("viact_known_pages"),
        selected_gap=selected_gap,
    )

    decision_logic = build_decision_logic(topic, research, content, references)
    content["decision_logic"] = decision_logic

    print("   Content suite generated.")

    # ── Push to Sheets ─────────────────────────────────────────────────────────
    print()
    print("── Pushing to Google Sheets (Webpage Content tab) ───────────────")
    competitor_urls_used = [a["url"] for a in research.get("competitor_analyses", [])]

    push_webpage(
        content=content,
        decision_logic=decision_logic,
        input_source=source_label,
        competitor_urls=competitor_urls_used,
        autorun_num=args.autorun,
        unverified=unverified,
    )
    print("   1 row written to 'Webpage Content' tab.")

    # ── Final Report ───────────────────────────────────────────────────────────
    print()
    print("══════════════════════════════════════════════════════════════════")
    print("  DONE — Content Suite Ready")
    print("══════════════════════════════════════════════════════════════════")
    print()
    seo = content.get("seo_suite", {})
    print(f"  Topic          : {content.get('topic', topic)}")
    print(f"  Primary KW     : {seo.get('primary_keyword', '')}")
    print(f"  Meta Title     : {seo.get('meta_title', '')}")
    print(f"  Schema FAQs    : {len(content.get('schema_faqs', []))} items")
    print(f"  Unverified     : {'Yes — add reference source' if unverified else 'No'}")
    print()
    print("── DECISION LOGIC (copy to Gary/Surendra's email) ───────────────")
    print()
    print(f"  {decision_logic}")
    print()
    print(f"  View sheet: {SHEET_ID_LINK}")
    print()


def main():
    parser = argparse.ArgumentParser(description="viact.ai content generation pipeline")

    # Input source — mutually exclusive
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url",   help="URL to scrape")
    group.add_argument("--brief", help="Plain-text topic brief")
    group.add_argument("--file",  help="Path to .txt/.pdf/.docx document")

    # Mode selection
    parser.add_argument(
        "--mode", choices=["social", "webpage"], default="social",
        help="Pipeline mode: 'social' (default) or 'webpage' (Manager-Ready)"
    )

    # Webpage mode options
    parser.add_argument(
        "--competitors", default="",
        help="Comma-separated competitor URLs (webpage mode — skips HITL Gate 1)"
    )
    parser.add_argument(
        "--autorun", type=int, default=None,
        help="Autorun number for weekly tracking (webpage mode)"
    )

    args = parser.parse_args()

    if args.mode == "social":
        run_social(args)
    else:
        run_webpage(args)


if __name__ == "__main__":
    main()
